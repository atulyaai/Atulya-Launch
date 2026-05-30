"""Server health dashboard — aggregated system health endpoint."""

import datetime
from pathlib import Path
from fastapi import APIRouter, Depends

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/health", tags=["health"])


def _check_service(name: str) -> dict:
    result = utils.run_command(["systemctl", "is-active", name], check=False)
    active = result is not None and result.returncode == 0 and "active" in (result.stdout or "")
    return {"name": name, "active": active, "status": "running" if active else "stopped"}


def _get_uptime() -> dict:
    try:
        import psutil
        boot = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot
        hours = uptime.total_seconds() / 3600
        return {
            "boot_time": boot.isoformat(),
            "uptime_hours": round(hours, 2),
            "uptime_human": f"{int(hours // 24)}d {int(hours % 24)}h {int((hours * 60) % 60)}m",
        }
    except ImportError:
        return {"boot_time": None, "uptime_hours": 0, "uptime_human": "unknown"}


def _get_load_average() -> dict:
    try:
        import os
        load1, load5, load15 = os.getloadavg()
        return {"load_1m": round(load1, 2), "load_5m": round(load5, 2), "load_15m": round(load15, 2)}
    except (OSError, ImportError):
        return {"load_1m": 0, "load_5m": 0, "load_15m": 0}


def _get_disk_info() -> dict:
    try:
        import psutil
        disk = psutil.disk_usage("/")
        return {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
            "total_human": f"{disk.total // (1024**3)} GB",
            "used_human": f"{disk.used // (1024**3)} GB",
            "free_human": f"{disk.free // (1024**3)} GB",
        }
    except ImportError:
        return {"total": 0, "used": 0, "free": 0, "percent": 0}


def _get_memory_info() -> dict:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
            "total_human": f"{mem.total // (1024**3)} GB",
            "used_human": f"{mem.used // (1024**3)} GB",
        }
    except ImportError:
        return {"total": 0, "available": 0, "used": 0, "percent": 0}


def _get_cpu_info() -> dict:
    try:
        import psutil
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "count": psutil.cpu_count(),
            "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        }
    except ImportError:
        return {"percent": 0, "count": 0, "freq": 0}


def _get_network_info() -> dict:
    try:
        import psutil
        net = psutil.net_io_counters()
        return {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "bytes_sent_human": f"{net.bytes_sent // (1024**2)} MB",
            "bytes_recv_human": f"{net.bytes_recv // (1024**2)} MB",
        }
    except ImportError:
        return {"bytes_sent": 0, "bytes_recv": 0}


def _check_ssl_expiry() -> list:
    ssl_certs = utils.load_config().get("ssl", {})
    result = []
    for domain, cert_data in ssl_certs.items():
        expires_at = cert_data.get("expires_at")
        days_left = None
        if expires_at:
            try:
                exp = datetime.datetime.fromisoformat(expires_at)
                days_left = (exp - datetime.datetime.now()).days
            except (ValueError, TypeError):
                pass
        result.append({
            "domain": domain,
            "expires_at": expires_at,
            "days_left": days_left,
            "status": "valid" if days_left and days_left > 0 else "expired" if days_left is not None else "unknown",
        })
    return result


def _check_backups() -> dict:
    backup_dir = utils.CONFIG_DIR / "backups"
    if not backup_dir.exists():
        return {"count": 0, "latest": None, "total_size": 0}
    backups = []
    total_size = 0
    for item in backup_dir.iterdir():
        if item.is_dir():
            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            total_size += size
            backups.append({"name": item.name, "size": size, "created": datetime.datetime.fromtimestamp(item.stat().st_mtime).isoformat()})
    backups.sort(key=lambda b: b["created"], reverse=True)
    return {
        "count": len(backups),
        "latest": backups[0] if backups else None,
        "total_size": total_size,
        "total_size_human": f"{total_size // (1024**2)} MB",
    }


def _calculate_security_score() -> dict:
    score = 100
    checks = []
    config = utils.load_config()
    auth_cfg = config.get("web", {}).get("auth", {})
    if not auth_cfg.get("admin_password_hash"):
        score -= 20
        checks.append({"name": "admin_password", "status": "fail", "points": -20})
    else:
        checks.append({"name": "admin_password", "status": "pass", "points": 0})
    if config.get("firewall", {}).get("enabled", False):
        checks.append({"name": "firewall", "status": "pass", "points": 0})
    else:
        score -= 15
        checks.append({"name": "firewall", "status": "fail", "points": -15})
    if config.get("ssl", {}):
        checks.append({"name": "ssl_certs", "status": "pass", "points": 0})
    else:
        score -= 10
        checks.append({"name": "ssl_certs", "status": "warn", "points": -10})
    ssh_config = config.get("ssh", {})
    if not ssh_config.get("password_auth", True):
        checks.append({"name": "ssh_key_only", "status": "pass", "points": 0})
    else:
        score -= 5
        checks.append({"name": "ssh_key_only", "status": "warn", "points": -5})
    return {"score": max(0, score), "max_score": 100, "checks": checks}


@router.get("")
def health_dashboard(user: dict = Depends(get_current_user)):
    services = [
        _check_service("nginx"),
        _check_service("mysql"),
        _check_service("postgresql"),
        _check_service("redis-server"),
        _check_service("memcached"),
        _check_service("postfix"),
        _check_service("dovecot"),
        _check_service("php-fpm"),
    ]
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "cpu": _get_cpu_info(),
        "memory": _get_memory_info(),
        "disk": _get_disk_info(),
        "network": _get_network_info(),
        "uptime": _get_uptime(),
        "load": _get_load_average(),
        "services": services,
        "ssl": _check_ssl_expiry(),
        "backups": _check_backups(),
        "security": _calculate_security_score(),
        "sites_count": len(utils.load_config().get("sites", {})),
        "databases_count": len(utils.load_config().get("databases", {})),
    }
