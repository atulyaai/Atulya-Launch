"""SSH access control configuration API."""

import json
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssh/access", tags=["ssh-access"])

SSH_CONFIG_FILE = utils.CONFIG_DIR / "ssh_access.json"

DEFAULT_SSH_CONFIG = {
    "port": 22,
    "allow_password_auth": True,
    "allow_root_login": True,
    "max_auth_tries": 6,
    "max_sessions": 10,
    "login_grace_time": 120,
    "permit_empty_passwords": False,
    "x11_forwarding": False,
    "allow_agent_forwarding": False,
    "client_alive_interval": 300,
    "client_alive_count_max": 3,
    "allowed_users": [],
    "allowed_groups": [],
    "protocol": 2,
}


def _load_ssh_config() -> dict:
    if SSH_CONFIG_FILE.exists():
        with open(SSH_CONFIG_FILE, "r") as f:
            stored = json.load(f) or {}
            config = DEFAULT_SSH_CONFIG.copy()
            config.update(stored)
            return config
    return DEFAULT_SSH_CONFIG.copy()


def _save_ssh_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SSH_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _apply_ssh_config(config: dict):
    if not utils.is_linux():
        return

    sshd_config_path = "/etc/ssh/sshd_config"
    try:
        with open(sshd_config_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        return

    settings = {
        "Port": str(config.get("port", 22)),
        "PermitRootLogin": "yes" if config.get("allow_root_login") else "no",
        "PasswordAuthentication": "yes" if config.get("allow_password_auth") else "no",
        "MaxAuthTries": str(config.get("max_auth_tries", 6)),
        "MaxSessions": str(config.get("max_sessions", 10)),
        "LoginGraceTime": str(config.get("login_grace_time", 120)),
        "PermitEmptyPasswords": "yes" if config.get("permit_empty_passwords") else "no",
        "X11Forwarding": "yes" if config.get("x11_forwarding") else "no",
        "AllowAgentForwarding": "yes" if config.get("allow_agent_forwarding") else "no",
        "ClientAliveInterval": str(config.get("client_alive_interval", 300)),
        "ClientAliveCountMax": str(config.get("client_alive_count_max", 3)),
    }

    for key, value in settings.items():
        pattern = rf"^#?\s*{re.escape(key)}\s+.*$"
        replacement = f"{key} {value}"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            content += f"\n{replacement}"

    allowed_users = config.get("allowed_users", [])
    if allowed_users:
        users_str = " ".join(allowed_users)
        pattern = r"^#?\s*AllowUsers\s+.*$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f"AllowUsers {users_str}", content, flags=re.MULTILINE)
        else:
            content += f"\nAllowUsers {users_str}"

    with open(sshd_config_path, "w") as f:
        f.write(content)

    utils.run_command(["sshd", "-t"], check=False)
    utils.service_action("restart", "ssh")


class SSHAccessUpdate(BaseModel):
    port: Optional[int] = None
    allow_password_auth: Optional[bool] = None
    allow_root_login: Optional[bool] = None
    max_auth_tries: Optional[int] = None
    max_sessions: Optional[int] = None
    login_grace_time: Optional[int] = None
    permit_empty_passwords: Optional[bool] = None
    x11_forwarding: Optional[bool] = None
    allow_agent_forwarding: Optional[bool] = None
    client_alive_interval: Optional[int] = None
    client_alive_count_max: Optional[int] = None
    allowed_users: Optional[list] = None
    allowed_groups: Optional[list] = None


@router.get("")
def get_ssh_access(user: dict = Depends(get_current_user)):
    config = _load_ssh_config()
    return {"config": config}


@router.put("")
def update_ssh_access(body: SSHAccessUpdate, user: dict = Depends(get_current_user)):
    config = _load_ssh_config()

    if body.port is not None:
        if body.port < 1 or body.port > 65535:
            raise HTTPException(status_code=400, detail="Port must be between 1 and 65535")
        config["port"] = body.port
    if body.allow_password_auth is not None:
        config["allow_password_auth"] = body.allow_password_auth
    if body.allow_root_login is not None:
        config["allow_root_login"] = body.allow_root_login
    if body.max_auth_tries is not None:
        config["max_auth_tries"] = body.max_auth_tries
    if body.max_sessions is not None:
        config["max_sessions"] = body.max_sessions
    if body.login_grace_time is not None:
        config["login_grace_time"] = body.login_grace_time
    if body.permit_empty_passwords is not None:
        config["permit_empty_passwords"] = body.permit_empty_passwords
    if body.x11_forwarding is not None:
        config["x11_forwarding"] = body.x11_forwarding
    if body.allow_agent_forwarding is not None:
        config["allow_agent_forwarding"] = body.allow_agent_forwarding
    if body.client_alive_interval is not None:
        config["client_alive_interval"] = body.client_alive_interval
    if body.client_alive_count_max is not None:
        config["client_alive_count_max"] = body.client_alive_count_max
    if body.allowed_users is not None:
        config["allowed_users"] = body.allowed_users
    if body.allowed_groups is not None:
        config["allowed_groups"] = body.allowed_groups

    _save_ssh_config(config)

    try:
        _apply_ssh_config(config)
    except Exception as e:
        return {"status": "saved_but_not_applied", "config": config, "error": str(e)}

    return {"status": "updated", "config": config}
