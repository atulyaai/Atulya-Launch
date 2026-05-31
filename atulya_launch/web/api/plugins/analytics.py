"""Usage Analytics - Bandwidth, email, DB QPS, resource usage history."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

ANALYTICS_DIR = utils.CONFIG_DIR / "analytics"
METRICS_FILE = ANALYTICS_DIR / "metrics.json"


def _ensure_dirs():
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    if not METRICS_FILE.exists():
        METRICS_FILE.write_text(json.dumps([], indent=2))


def _load_metrics() -> list:
    _ensure_dirs()
    return json.loads(METRICS_FILE.read_text())


def _save_metrics(data: list):
    _ensure_dirs()
    METRICS_FILE.write_text(json.dumps(data, indent=2))


def _append_metric(name: str, value: float, tags: dict = None):
    metrics = _load_metrics()
    metrics.append({
        "name": name,
        "value": value,
        "timestamp": datetime.now().isoformat(),
        "tags": tags or {},
    })
    cutoff = datetime.now() - timedelta(days=30)
    metrics = [m for m in metrics if datetime.fromisoformat(m["timestamp"]) > cutoff]
    _save_metrics(metrics)


def _collect_metrics():
    import psutil

    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    _append_metric("cpu_percent", cpu)
    _append_metric("memory_percent", mem.percent)
    _append_metric("memory_used_mb", mem.used / 1048576)
    _append_metric("disk_percent", disk.percent)
    _append_metric("disk_used_gb", disk.used / (1024 ** 3))
    _append_metric("net_bytes_sent", net.bytes_sent)
    _append_metric("net_bytes_recv", net.bytes_recv)

    load = [0, 0, 0]
    try:
        load = list(psutil.getloadavg())
    except (AttributeError, OSError):
        pass
    _append_metric("load_1min", load[0])
    _append_metric("load_5min", load[1])
    _append_metric("load_15min", load[2])


class TimeRange(BaseModel):
    hours: int = 24
    metric: Optional[str] = None


@router.get("/collect")
def trigger_collect(user: dict = Depends(get_current_user)):
    try:
        _collect_metrics()
        return {"status": "collected"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/dashboard")
def get_dashboard(user: dict = Depends(get_current_user)):
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()

        load = [0, 0, 0]
        try:
            load = list(psutil.getloadavg())
        except (AttributeError, OSError):
            pass

        processes = len(psutil.pids())

        _append_metric("cpu_percent", cpu)
        _append_metric("memory_percent", mem.percent)
        _append_metric("disk_percent", disk.percent)

        return {
            "cpu": {
                "percent": cpu,
                "cores": psutil.cpu_count(),
                "load_1m": load[0],
                "load_5m": load[1],
                "load_15m": load[2],
            },
            "memory": {
                "percent": mem.percent,
                "total_mb": round(mem.total / 1048576),
                "used_mb": round(mem.used / 1048576),
                "available_mb": round(mem.available / 1048576),
            },
            "disk": {
                "percent": disk.percent,
                "total_gb": round(disk.total / (1024 ** 3), 2),
                "used_gb": round(disk.used / (1024 ** 3), 2),
                "free_gb": round(disk.free / (1024 ** 3), 2),
            },
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
                "packets_sent": net.packets_sent,
                "packets_recv": net.packets_recv,
            },
            "processes": processes,
            "timestamp": datetime.now().isoformat(),
        }
    except ImportError:
        return {"error": "psutil not installed", "dashboard": {}}


@router.get("/metrics")
def get_metrics(hours: int = 24, metric: Optional[str] = None, user: dict = Depends(get_current_user)):
    metrics = _load_metrics()
    cutoff = datetime.now() - timedelta(hours=hours)
    metrics = [m for m in metrics if datetime.fromisoformat(m["timestamp"]) > cutoff]

    if metric:
        metrics = [m for m in metrics if m["name"] == metric]

    by_name = {}
    for m in metrics:
        name = m["name"]
        if name not in by_name:
            by_name[name] = []
        by_name[name].append({
            "value": m["value"],
            "timestamp": m["timestamp"],
        })

    return {
        "metrics": by_name,
        "total_points": len(metrics),
        "hours": hours,
    }


@router.get("/bandwidth")
def get_bandwidth(user: dict = Depends(get_current_user)):
    metrics = _load_metrics()
    sent = [m for m in metrics if m["name"] == "net_bytes_sent"]
    recv = [m for m in metrics if m["name"] == "net_bytes_recv"]

    total_sent = sent[-1]["value"] if sent else 0
    total_recv = recv[-1]["value"] if recv else 0

    hourly_sent = []
    hourly_recv = []
    now = datetime.now()
    for i in range(24):
        hour_start = now - timedelta(hours=i + 1)
        hour_end = now - timedelta(hours=i)
        s = [m for m in sent if hour_start.isoformat() < m["timestamp"] < hour_end.isoformat()]
        r = [m for m in recv if hour_start.isoformat() < m["timestamp"] < hour_end.isoformat()]
        hourly_sent.append({
            "hour": hour_start.strftime("%H:00"),
            "bytes": s[-1]["value"] - s[0]["value"] if len(s) >= 2 else 0,
        })
        hourly_recv.append({
            "hour": hour_start.strftime("%H:00"),
            "bytes": r[-1]["value"] - r[0]["value"] if len(r) >= 2 else 0,
        })

    return {
        "total_sent_gb": round(total_sent / (1024 ** 3), 3),
        "total_recv_gb": round(total_recv / (1024 ** 3), 3),
        "hourly_sent": hourly_sent,
        "hourly_recv": hourly_recv,
    }


@router.get("/processes/top")
def top_processes(limit: int = 10, sort_by: str = "cpu", user: dict = Depends(get_current_user)):
    import psutil

    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'username']):
        try:
            info = proc.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu_percent": info["cpu_percent"] or 0,
                "memory_percent": round(info["memory_percent"] or 0, 1),
                "status": info["status"],
                "username": info["username"] or "system",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if sort_by == "cpu":
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
    elif sort_by == "memory":
        procs.sort(key=lambda x: x["memory_percent"], reverse=True)
    elif sort_by == "name":
        procs.sort(key=lambda x: x["name"].lower())

    return {"processes": procs[:limit], "total": len(procs)}


@router.get("/health")
def system_health(user: dict = Depends(get_current_user)):
    import psutil

    checks = []
    score = 100

    cpu = psutil.cpu_percent(interval=0.1)
    if cpu > 90:
        checks.append({"name": "CPU", "status": "critical", "message": f"CPU usage at {cpu}%"})
        score -= 20
    elif cpu > 70:
        checks.append({"name": "CPU", "status": "warning", "message": f"CPU usage at {cpu}%"})
        score -= 5
    else:
        checks.append({"name": "CPU", "status": "healthy", "message": f"CPU usage at {cpu}%"})

    mem = psutil.virtual_memory()
    if mem.percent > 90:
        checks.append({"name": "Memory", "status": "critical", "message": f"Memory usage at {mem.percent}%"})
        score -= 20
    elif mem.percent > 80:
        checks.append({"name": "Memory", "status": "warning", "message": f"Memory usage at {mem.percent}%"})
        score -= 5
    else:
        checks.append({"name": "Memory", "status": "healthy", "message": f"Memory usage at {mem.percent}%"})

    disk = psutil.disk_usage("/")
    if disk.percent > 95:
        checks.append({"name": "Disk", "status": "critical", "message": f"Disk usage at {disk.percent}%"})
        score -= 20
    elif disk.percent > 85:
        checks.append({"name": "Disk", "status": "warning", "message": f"Disk usage at {disk.percent}%"})
        score -= 5
    else:
        checks.append({"name": "Disk", "status": "healthy", "message": f"Disk usage at {disk.percent}%"})

    services_to_check = ["nginx", "mariadb", "redis-server", "postfix", "fail2ban"]
    for svc in services_to_check:
        exists = utils.service_exists(svc)
        if exists:
            checks.append({"name": svc, "status": "healthy", "message": f"{svc} is running"})
        else:
            checks.append({"name": svc, "status": "warning", "message": f"{svc} is not running"})
            score -= 2

    score = max(0, min(100, score))

    return {
        "score": score,
        "grade": "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F",
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/summary")
def analytics_summary(user: dict = Depends(get_current_user)):
    metrics = _load_metrics()
    now = datetime.now()

    last_hour = [m for m in metrics if datetime.fromisoformat(m["timestamp"]) > now - timedelta(hours=1)]
    last_day = [m for m in metrics if datetime.fromisoformat(m["timestamp"]) > now - timedelta(days=1)]

    avg_cpu_hour = sum(m["value"] for m in last_hour if m["name"] == "cpu_percent") / max(1, len([m for m in last_hour if m["name"] == "cpu_percent"]))
    avg_cpu_day = sum(m["value"] for m in last_day if m["name"] == "cpu_percent") / max(1, len([m for m in last_day if m["name"] == "cpu_percent"]))

    return {
        "total_data_points": len(metrics),
        "cpu_avg_1h": round(avg_cpu_hour, 1),
        "cpu_avg_24h": round(avg_cpu_day, 1),
        "metrics_tracked": list(set(m["name"] for m in metrics)),
    }
