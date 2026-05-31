"""Server control API - reboot, shutdown, hostname."""

import platform
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/server", tags=["server-control"])


class HostnameRequest(BaseModel):
    hostname: str


@router.post("/reboot")
def reboot_server(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Reboot is only supported on Linux")

    result = utils.run_command(["shutdown", "-r", "now"], check=False)
    if result and result.returncode != 0:
        try:
            result = utils.run_command(["sudo", "reboot"], check=False)
        except Exception:
            pass

    return {"status": "reboot_initiated", "message": "Server will reboot shortly"}


@router.post("/shutdown")
def shutdown_server(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Shutdown is only supported on Linux")

    result = utils.run_command(["shutdown", "-h", "now"], check=False)
    if result and result.returncode != 0:
        try:
            result = utils.run_command(["sudo", "shutdown", "-h", "now"], check=False)
        except Exception:
            pass

    return {"status": "shutdown_initiated", "message": "Server will shutdown shortly"}


@router.post("/hostname")
def set_hostname(body: HostnameRequest, user: dict = Depends(get_current_user)):
    if not body.hostname or len(body.hostname) > 253:
        raise HTTPException(status_code=400, detail="Invalid hostname")

    import re
    if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$", body.hostname):
        raise HTTPException(status_code=400, detail="Invalid hostname format")

    old_hostname = platform.node()

    if utils.is_linux():
        hostnamectl = utils.run_command(["hostnamectl", "set-hostname", body.hostname], check=False)
        if hostnamectl and hostnamectl.returncode != 0:
            utils.run_command(["hostname", body.hostname], check=False)

        hosts_path = "/etc/hosts"
        try:
            with open(hosts_path, "r") as f:
                content = f.read()
            content = content.replace(old_hostname, body.hostname)
            with open(hosts_path, "w") as f:
                f.write(content)
        except Exception:
            pass
    else:
        raise HTTPException(status_code=400, detail="Hostname change is only supported on Linux")

    return {"status": "hostname_changed", "old_hostname": old_hostname, "new_hostname": body.hostname}


@router.get("/info")
def server_info(user: dict = Depends(get_current_user)):
    import datetime
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = (datetime.datetime.now() - boot_time).total_seconds()
    except ImportError:
        mem = None
        disk = None
        uptime = 0

    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "uptime_seconds": round(uptime),
        "memory_percent": mem.percent if mem else None,
        "disk_percent": disk.percent if disk else None,
    }
