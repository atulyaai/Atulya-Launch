"""Background job scheduler using APScheduler with SQLite job store."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from ..web.database import connect, audit_log


_scheduler = None


def get_scheduler():
    """Get or create the APScheduler instance."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        db_path = os.path.join(os.path.dirname(__file__), "..", "..", "panel.db")
        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")
        }
        _scheduler = BackgroundScheduler(jobstores=jobstores)
        return _scheduler
    except ImportError:
        return None


def start_scheduler():
    """Start the background scheduler if available."""
    scheduler = get_scheduler()
    if scheduler is None:
        return False
    if not scheduler.running:
        scheduler.start()
    _register_default_jobs()
    return True


def _register_default_jobs():
    """Register the default background jobs."""
    scheduler = get_scheduler()
    if scheduler is None:
        return

    jobs = [
        {
            "id": "ssl_auto_renew",
            "func": _job_ssl_auto_renew,
            "trigger": "cron",
            "hour": 3,
            "minute": 0,
            "name": "SSL Certificate Auto-Renewal",
        },
        {
            "id": "backup_cleanup",
            "func": _job_backup_cleanup,
            "trigger": "cron",
            "hour": 4,
            "minute": 0,
            "name": "Old Backup Cleanup",
        },
        {
            "id": "session_cleanup",
            "func": _job_session_cleanup,
            "trigger": "interval",
            "hours": 1,
            "name": "Expired Session Cleanup",
        },
        {
            "id": "rate_limit_cleanup",
            "func": _job_rate_limit_cleanup,
            "trigger": "interval",
            "minutes": 15,
            "name": "Rate Limit Cleanup",
        },
        {
            "id": "disk_usage_check",
            "func": _job_disk_usage_check,
            "trigger": "interval",
            "minutes": 30,
            "name": "Disk Usage Monitor",
        },
    ]

    for job in jobs:
        try:
            scheduler.add_job(
                func=job["func"],
                trigger=job.get("trigger", "interval"),
                id=job["id"],
                name=job["name"],
                replace_existing=True,
                **{k: v for k, v in job.items() if k not in ("id", "func", "trigger", "name")},
            )
        except Exception:
            pass


def _job_ssl_auto_renew():
    """Background job: auto-renew SSL certificates expiring within 30 days."""
    try:
        import subprocess
        result = subprocess.run(
            ["certbot", "renew", "--quiet", "--deploy-hook", "systemctl reload nginx"],
            capture_output=True, text=True, timeout=300
        )
        audit_log("system", "job.ssl_renew", "ok" if result.returncode == 0 else "failed", {"output": result.stdout[:500]})
    except Exception as e:
        audit_log("system", "job.ssl_renew", "error", {"error": str(e)})


def _job_backup_cleanup():
    """Background job: remove backups older than 30 days."""
    try:
        from pathlib import Path
        import time
        backups_dir = Path(os.path.expanduser("~/.atulya-launch/backups"))
        if not backups_dir.exists():
            return
        cutoff = time.time() - (30 * 86400)
        removed = 0
        for f in backups_dir.glob("*.zip"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        audit_log("system", "job.backup_cleanup", "ok", {"removed": removed})
    except Exception as e:
        audit_log("system", "job.backup_cleanup", "error", {"error": str(e)})


def _job_session_cleanup():
    """Background job: remove expired sessions."""
    try:
        with connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?",
                (datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",)
            )
            removed = cursor.rowcount
            conn.commit()
        audit_log("system", "job.session_cleanup", "ok", {"removed": removed})
    except Exception as e:
        audit_log("system", "job.session_cleanup", "error", {"error": str(e)})


def _job_rate_limit_cleanup():
    """Background job: clean up old rate limit entries."""
    try:
        import time
        cutoff = time.time() - 3600
        with connect() as conn:
            cursor = conn.execute(
                "DELETE FROM rate_limit_attempts WHERE timestamp < ?",
                (cutoff,)
            )
            removed = cursor.rowcount
            conn.commit()
        audit_log("system", "job.rate_limit_cleanup", "ok", {"removed": removed})
    except Exception as e:
        audit_log("system", "job.rate_limit_cleanup", "error", {"error": str(e)})


def _job_disk_usage_check():
    """Background job: check disk usage and alert if >80%."""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        percent = (used / total) * 100 if total else 0
        if percent > 80:
            audit_log("system", "job.disk_alert", "warning", {"percent": round(percent, 1), "total": total, "used": used})
        audit_log("system", "job.disk_check", "ok", {"percent": round(percent, 1)})
    except Exception as e:
        audit_log("system", "job.disk_check", "error", {"error": str(e)})


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown()
    _scheduler = None


def get_jobs() -> list[dict[str, Any]]:
    """List all scheduled jobs."""
    scheduler = get_scheduler()
    if scheduler is None:
        return []
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs
