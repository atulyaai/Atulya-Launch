"""Database Backup Schedule API."""

import json
import subprocess
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/databases", tags=["db-backup-schedule"])

DB_SCHEDULE_FILE = utils.CONFIG_DIR / "db_backup_schedules.json"
CRON_TAG = "# atulya-db-backup"


def _load_schedules() -> dict:
    if DB_SCHEDULE_FILE.exists():
        with open(DB_SCHEDULE_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_schedules(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(DB_SCHEDULE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _cron_time_for_schedule(schedule: dict) -> str:
    freq = schedule.get("frequency", "daily")
    time_str = schedule.get("time", "02:00")
    hour, minute = time_str.split(":")

    if freq == "daily":
        return f"{minute} {hour} * * *"
    elif freq == "weekly":
        day = schedule.get("day_of_week", 0)
        return f"{minute} {hour} * * {day}"
    elif freq == "monthly":
        day = schedule.get("day_of_month", 1)
        return f"{minute} {hour} {day} * *"
    return f"{minute} {hour} * * *"


def _backup_script(db_name: str, db_type: str, backup_dir: str) -> str:
    if db_type == "mysql":
        return f"""#!/bin/bash
DB_NAME="{db_name}"
BACKUP_DIR="{backup_dir}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
mysqldump --single-transaction --routines --triggers "$DB_NAME" | gzip > "$BACKUP_DIR/$DB_NAME_$TIMESTAMP.sql.gz"
find "$BACKUP_DIR" -name "$DB_NAME_*.sql.gz" -mtime +30 -delete
"""
    elif db_type == "postgresql":
        return f"""#!/bin/bash
DB_NAME="{db_name}"
BACKUP_DIR="{backup_dir}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
sudo -u postgres pg_dump "$DB_NAME" | gzip > "$BACKUP_DIR/$DB_NAME_$TIMESTAMP.sql.gz"
find "$BACKUP_DIR" -name "$DB_NAME_*.sql.gz" -mtime +30 -delete
"""
    return ""


def _update_cron(db_name: str, schedule: dict, enabled: bool):
    result = utils.run_command(["crontab", "-l"], check=False)
    existing = result.stdout if result and result.returncode == 0 else ""
    lines = [l for l in existing.splitlines() if not (CRON_TAG in l and db_name in l)]

    if enabled and schedule.get("enabled", True):
        backup_dir = str(utils.CONFIG_DIR / "backups" / "db_scheduled")
        script = _backup_script(db_name, schedule.get("db_type", "mysql"), backup_dir)
        script_path = str(utils.CONFIG_DIR / "scripts" / f"db_backup_{db_name}.sh")
        utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (utils.CONFIG_DIR / "scripts").mkdir(exist_ok=True)
        with open(script_path, "w") as f:
            f.write(script)
        result = utils.run_command(["chmod", "+x", script_path], check=False)

        cron_time = _cron_time_for_schedule(schedule)
        lines.append(f"{cron_time} /bin/bash {script_path} {CRON_TAG} {db_name}")

    new_crontab = "\n".join(lines) + "\n" if lines else ""
    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
    proc.communicate(input=new_crontab)


class ScheduleSet(BaseModel):
    frequency: str = "daily"
    time: str = "02:00"
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    enabled: bool = True
    keep_days: int = 30


@router.get("/{db}/schedule")
def get_db_schedule(db: str, user: dict = Depends(get_current_user)):
    dbs = utils.load_config().get("databases", {})
    if db not in dbs:
        raise HTTPException(status_code=404, detail="Database not found")

    schedules = _load_schedules()
    schedule = schedules.get(db)
    if not schedule:
        return {"database": db, "schedule": None, "message": "No backup schedule configured"}

    return {"database": db, "schedule": schedule}


@router.post("/{db}/schedule")
def set_db_schedule(db: str, body: ScheduleSet, user: dict = Depends(get_current_user)):
    dbs = utils.load_config().get("databases", {})
    if db not in dbs:
        raise HTTPException(status_code=404, detail="Database not found")

    if body.frequency not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="Frequency must be daily, weekly, or monthly")

    try:
        parts = body.time.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM (24h)")

    if body.frequency == "weekly" and body.day_of_week is not None:
        if not (0 <= body.day_of_week <= 6):
            raise HTTPException(status_code=400, detail="day_of_week must be 0-6 (Sun-Sat)")
    if body.frequency == "monthly" and body.day_of_month is not None:
        if not (1 <= body.day_of_month <= 31):
            raise HTTPException(status_code=400, detail="day_of_month must be 1-31")

    schedule = {
        "frequency": body.frequency,
        "time": body.time,
        "day_of_week": body.day_of_week,
        "day_of_month": body.day_of_month,
        "enabled": body.enabled,
        "keep_days": body.keep_days,
        "db_type": dbs[db].get("type", "mysql"),
        "created_at": datetime.now().isoformat(),
    }

    schedules = _load_schedules()
    schedules[db] = schedule
    _save_schedules(schedules)

    _update_cron(db, schedule, body.enabled)

    return {"status": "scheduled", "database": db, "schedule": schedule}


@router.delete("/{db}/schedule")
def delete_db_schedule(db: str, user: dict = Depends(get_current_user)):
    schedules = _load_schedules()
    if db not in schedules:
        raise HTTPException(status_code=404, detail="No schedule found for this database")

    schedule = schedules.pop(db)
    _save_schedules(schedules)
    _update_cron(db, schedule, enabled=False)

    return {"status": "deleted", "database": db}


@router.get("/{db}/schedule/backups")
def list_scheduled_backups(db: str, user: dict = Depends(get_current_user)):
    backup_dir = utils.CONFIG_DIR / "backups" / "db_scheduled"
    if not backup_dir.exists():
        return {"database": db, "backups": []}

    backups = []
    for f in sorted(backup_dir.glob(f"{db}_*.sql.gz"), reverse=True):
        stat = f.stat()
        backups.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return {"database": db, "backups": backups[:50]}
