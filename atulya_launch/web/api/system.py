"""System information and services API."""

import os
import platform
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/info")
def system_info(user: dict = Depends(get_current_user)):
    import psutil
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot = __import__("datetime").datetime.fromtimestamp(psutil.boot_time())
    uptime = (__import__("datetime").datetime.now() - boot).total_seconds()
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "memory_total_mb": round(mem.total / 1048576),
        "memory_used_mb": round(mem.used / 1048576),
        "memory_percent": mem.percent,
        "disk_total_gb": round(disk.total / 1073741824, 2),
        "disk_used_gb": round(disk.used / 1073741824, 2),
        "disk_percent": disk.percent,
        "uptime_seconds": round(uptime),
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
    }


@router.get("/services")
def list_services(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        return {"services": [], "note": "Service listing only on Linux"}
    result = utils.run_command(
        ["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend", "--plain"],
        check=False,
    )
    services = []
    if result and result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 4:
                services.append({
                    "name": parts[0].replace(".service", ""),
                    "load": parts[1],
                    "active": parts[2],
                    "sub": parts[3],
                    "description": parts[4] if len(parts) > 4 else "",
                })
    return {"services": services}


@router.post("/services/{name}/start")
def start_service(name: str, user: dict = Depends(get_current_user)):
    result = utils.service_action("start", name)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to start {name}")
    return {"status": "started", "service": name}


@router.post("/services/{name}/stop")
def stop_service(name: str, user: dict = Depends(get_current_user)):
    result = utils.service_action("stop", name)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to stop {name}")
    return {"status": "stopped", "service": name}


@router.post("/services/{name}/restart")
def restart_service(name: str, user: dict = Depends(get_current_user)):
    result = utils.service_action("restart", name)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to restart {name}")
    return {"status": "restarted", "service": name}


@router.get("/updates")
def check_updates(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        return {"updates": [], "note": "Update check only on Linux"}
    result = utils.run_command(
        ["apt", "list", "--upgradable"],
        check=False,
    )
    updates = []
    if result and result.returncode == 0:
        for line in result.stdout.splitlines()[1:]:
            if "/" in line:
                updates.append(line.split()[0])
    return {"updates": updates, "count": len(updates)}
