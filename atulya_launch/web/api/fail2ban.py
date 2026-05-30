"""Fail2ban Management API."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/fail2ban", tags=["fail2ban"])

F2B_CONFIG_FILE = utils.CONFIG_DIR / "fail2ban.json"

JAIL_CONF = "/etc/fail2ban/jail.local"


def _load_f2b_config() -> dict:
    if F2B_CONFIG_FILE.exists():
        with open(F2B_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_f2b_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(F2B_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _f2b_installed() -> bool:
    result = utils.run_command(["fail2ban-client", "--version"], check=False)
    return result is not None and result.returncode == 0


def _f2b_running() -> bool:
    result = utils.run_command(["fail2ban-client", "ping"], check=False)
    return result is not None and result.returncode == 0 and "pong" in (result.stdout or "")


def _get_f2b_status() -> dict:
    result = utils.run_command(["fail2ban-client", "status"], check=False)
    if not result or result.returncode != 0:
        return {"installed": _f2b_installed(), "running": False, "jails": []}

    lines = result.stdout.strip().split("\n")
    jails = []
    for line in lines:
        if "Jail list:" in line:
            jail_str = line.split(":", 1)[1].strip()
            jails = [j.strip() for j in jail_str.split(",") if j.strip()]

    return {
        "installed": True,
        "running": True,
        "jails": jails,
    }


def _get_jail_status(jail_name: str) -> dict:
    result = utils.run_command(["fail2ban-client", "status", jail_name], check=False)
    if not result or result.returncode != 0:
        return {"name": jail_name, "active": False}

    lines = result.stdout.strip().split("\n")
    info = {"name": jail_name, "active": True}
    for line in lines:
        if "Currently banned:" in line:
            info["currently_banned"] = int(line.split(":", 1)[1].strip())
        elif "Total banned:" in line:
            info["total_banned"] = int(line.split(":", 1)[1].strip())
        elif "Currently failed:" in line:
            info["currently_failed"] = int(line.split(":", 1)[1].strip())
        elif "Banned IP list:" in line:
            ip_str = line.split(":", 1)[1].strip()
            info["banned_ips"] = [ip.strip() for ip in ip_str.split() if ip.strip()]
    return info


def _get_all_banned() -> list:
    status = _get_f2b_status()
    all_banned = []
    for jail in status.get("jails", []):
        jail_info = _get_jail_status(jail)
        for ip in jail_info.get("banned_ips", []):
            all_banned.append({"ip": ip, "jail": jail})
    return all_banned


class Fail2banConfig(BaseModel):
    bantime: int = 3600
    findtime: int = 600
    maxretry: int = 5
    backend: str = "auto"


class JailEnable(BaseModel):
    enabled: bool = True
    port: str = "http,https"
    filter: str = ""
    logpath: str = ""
    maxretry: int = 5
    bantime: int = 3600
    findtime: int = 600


@router.get("/status")
def fail2ban_status(user: dict = Depends(get_current_user)):
    status = _get_f2b_status()
    config = _load_f2b_config()
    status["config"] = config
    return status


@router.post("/enable")
def enable_fail2ban(user: dict = Depends(get_current_user)):
    if not _f2b_installed():
        utils.run_command(["apt-get", "update", "-qq"], check=False)
        utils.run_command(["apt-get", "install", "-y", "-qq", "fail2ban"], check=False)
        if not _f2b_installed():
            raise HTTPException(status_code=500, detail="Failed to install fail2ban")

    utils.service_action("enable", "fail2ban")
    utils.service_action("start", "fail2ban")

    config = _load_f2b_config()
    config["enabled"] = True
    config["updated_at"] = datetime.now().isoformat()
    _save_f2b_config(config)

    return {"status": "enabled"}


@router.post("/disable")
def disable_fail2ban(user: dict = Depends(get_current_user)):
    utils.service_action("stop", "fail2ban")
    utils.service_action("disable", "fail2ban")

    config = _load_f2b_config()
    config["enabled"] = False
    config["updated_at"] = datetime.now().isoformat()
    _save_f2b_config(config)

    return {"status": "disabled"}


@router.get("/jails")
def list_jails(user: dict = Depends(get_current_user)):
    status = _get_f2b_status()
    jails = []
    for jail_name in status.get("jails", []):
        jails.append(_get_jail_status(jail_name))
    return {"jails": jails}


@router.post("/jails/{jail_name}/enable")
def enable_jail(jail_name: str, user: dict = Depends(get_current_user)):
    result = utils.run_command(["fail2ban-client", "start", jail_name], check=False)
    if not result or result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to enable jail {jail_name}")
    return {"status": "enabled", "jail": jail_name}


@router.post("/jails/{jail_name}/disable")
def disable_jail(jail_name: str, user: dict = Depends(get_current_user)):
    result = utils.run_command(["fail2ban-client", "stop", jail_name], check=False)
    if not result or result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to disable jail {jail_name}")
    return {"status": "disabled", "jail": jail_name}


@router.get("/banned")
def get_banned_ips(user: dict = Depends(get_current_user)):
    return {"banned": _get_all_banned()}


@router.post("/unban/{ip}")
def unban_ip(ip: str, user: dict = Depends(get_current_user)):
    result = utils.run_command(["fail2ban-client", "set", "*", "unbanip", ip], check=False)
    if result and result.returncode == 0:
        return {"status": "unbanned", "ip": ip}

    status = _get_f2b_status()
    for jail in status.get("jails", []):
        result = utils.run_command(["fail2ban-client", "set", jail, "unbanip", ip], check=False)
        if result and result.returncode == 0:
            return {"status": "unbanned", "ip": ip, "jail": jail}

    raise HTTPException(status_code=404, detail="IP not found in any jail")


@router.get("/logs")
def get_f2b_logs(lines: int = 100, user: dict = Depends(get_current_user)):
    log_path = "/var/log/fail2ban.log"
    if not Path(log_path).exists():
        return {"error": "fail2ban log not found", "lines": []}
    try:
        with open(log_path, "r", errors="replace") as f:
            all_lines = f.readlines()
        return {"lines": [l.rstrip() for l in all_lines[-lines:]]}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
