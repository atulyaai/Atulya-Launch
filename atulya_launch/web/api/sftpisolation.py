"""SSH/SFTP User Isolation API — chroot jail management."""

import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssh/isolation", tags=["ssh-isolation"])

ISOLATION_CONFIG_FILE = utils.CONFIG_DIR / "ssh_isolation.json"

SSHD_CONFIG = "/etc/ssh/sshd_config"
JAIL_BASE = "/var/jail"


def _load_isolation_config() -> dict:
    if ISOLATION_CONFIG_FILE.exists():
        with open(ISOLATION_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_isolation_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(ISOLATION_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _setup_chroot_jail(username: str, jail_dir: str) -> dict:
    jail_path = Path(jail_dir)
    required_dirs = ["dev", "etc", "home", "usr", "bin", "lib", "lib64", "tmp"]
    for d in required_dirs:
        (jail_path / d).mkdir(parents=True, exist_ok=True)

    dev_null = jail_path / "dev" / "null"
    if not dev_null.exists():
        dev_null.touch()
        os.chmod(dev_null, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)

    user_home = jail_path / "home" / username
    user_home.mkdir(parents=True, exist_ok=True)

    return {
        "jail_dir": str(jail_path),
        "user_home": str(user_home),
        "created_at": datetime.now().isoformat(),
    }


def _apply_sshd_config(jail_dir: str, enabled: bool) -> dict:
    if not Path(SSHD_CONFIG).exists():
        return {"error": "sshd_config not found"}

    result = utils.run_command(["cp", SSHD_CONFIG, SSHD_CONFIG + ".bak"], check=False)

    lines = []
    with open(SSHD_CONFIG, "r") as f:
        lines = f.readlines()

    new_lines = []
    in_match_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Match"):
            in_match_block = True
            new_lines.append(line)
            continue
        if in_match_block and (stripped.startswith("ChrootDirectory") or stripped.startswith("ForceCommand") or stripped.startswith("AllowTcpForwarding")):
            continue
        if in_match_block and not stripped.startswith(("ChrootDirectory", "ForceCommand", "AllowTcpForwarding")):
            in_match_block = False
        new_lines.append(line)

    if enabled:
        new_lines.append("\n")
        new_lines.append("Match User *,!root\n")
        new_lines.append(f"    ChrootDirectory {jail_dir}\n")
        new_lines.append("    ForceCommand internal-sftp\n")
        new_lines.append("    AllowTcpForwarding no\n")
        new_lines.append("    X11Forwarding no\n")

    with open(SSHD_CONFIG, "w") as f:
        f.writelines(new_lines)

    return {"status": "sshd_config_updated", "enabled": enabled}


def _get_isolation_status() -> dict:
    config = _load_isolation_config()
    enabled = config.get("enabled", False)
    jail_dir = config.get("jail_directory", JAIL_BASE)
    shell_access = config.get("shell_access_denied", True)

    sshd_result = utils.run_command(["sshd", "-T"], check=False)
    current_chroot = ""
    if sshd_result and sshd_result.returncode == 0:
        for line in sshd_result.stdout.splitlines():
            if line.strip().startswith("chrootdirectory"):
                current_chroot = line.split()[-1]

    return {
        "enabled": enabled,
        "jail_directory": jail_dir,
        "shell_access_denied": shell_access,
        "current_chroot": current_chroot,
        "jail_exists": Path(jail_dir).exists(),
    }


class IsolationConfig(BaseModel):
    enabled: bool = False
    jail_directory: str = JAIL_BASE
    allow_shell_access: bool = False


class IsolatedUser(BaseModel):
    username: str


@router.get("")
def get_isolation_status(user: dict = Depends(get_current_user)):
    return _get_isolation_status()


@router.put("")
def set_isolation_config(body: IsolationConfig, user: dict = Depends(get_current_user)):
    jail_dir = body.jail_directory or JAIL_BASE
    shell_access = not body.allow_shell_access

    config = {
        "enabled": body.enabled,
        "jail_directory": jail_dir,
        "shell_access_denied": shell_access,
        "updated_at": datetime.now().isoformat(),
    }
    _save_isolation_config(config)

    if body.enabled:
        jail_setup = _setup_chroot_jail("sftpuser", jail_dir)
        sshd_apply = _apply_sshd_config(jail_dir, True)
        if "error" in sshd_apply:
            raise HTTPException(status_code=500, detail=sshd_apply["error"])
        utils.service_action("restart", "sshd")
    else:
        sshd_apply = _apply_sshd_config(jail_dir, False)
        utils.service_action("restart", "sshd")

    return {"status": "updated", "isolation": config}


@router.post("/setup-jail")
def setup_jail(body: IsolatedUser, user: dict = Depends(get_current_user)):
    config = _load_isolation_config()
    jail_dir = config.get("jail_directory", JAIL_BASE)

    jail_setup = _setup_chroot_jail(body.username, jail_dir)

    user_home = Path(jail_setup["user_home"])
    (user_home / ".ssh").mkdir(parents=True, exist_ok=True)

    result = utils.run_command(
        ["useradd", "-d", str(user_home), "-s", "/usr/sbin/nologin", "-M", body.username],
        check=False,
    )

    return {
        "status": "jail_setup",
        "username": body.username,
        "jail_dir": jail_setup["jail_dir"],
        "user_home": jail_setup["user_home"],
    }


@router.get("/jailed-users")
def list_jailed_users(user: dict = Depends(get_current_user)):
    config = _load_isolation_config()
    jail_dir = config.get("jail_directory", JAIL_BASE)
    jail_path = Path(jail_dir)
    users = []
    if (jail_path / "home").exists():
        for entry in (jail_path / "home").iterdir():
            if entry.is_dir():
                users.append({
                    "username": entry.name,
                    "home": str(entry),
                })
    return {"users": users}
