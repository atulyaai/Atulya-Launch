"""Webmail - Roundcube integration plugin."""

import json
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/webmail", tags=["webmail"])

WEBMAIL_DIR = utils.CONFIG_DIR / "webmail"
CONFIG_FILE = WEBMAIL_DIR / "config.json"


def _ensure_dirs():
    WEBMAIL_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({
            "enabled": False,
            "provider": "roundcube",
            "skin": "elastic",
            "upload_max_size": 25,
            "autoresponder_available": True,
        }, indent=2))


def _load_config() -> dict:
    _ensure_dirs()
    return json.loads(CONFIG_FILE.read_text())


def _save_config(data: dict):
    _ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


class WebmailConfig(BaseModel):
    enabled: Optional[bool] = None
    skin: Optional[str] = "elastic"
    upload_max_size: Optional[int] = 25


class WebmailAccount(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = ""


def _install_roundcube() -> dict:
    if not utils.is_linux():
        return {"status": "error", "message": "Roundcube installation only supported on Linux"}

    result = utils.run_command(
        ["apt-get", "install", "-y", "roundcube", "roundcube-pgsql"],
        check=False,
    )

    nginx_config = """server {
    listen 80;
    server_name webmail.localhost;
    root /usr/share/roundcube;
    index index.php index.html;

    location ~ \\.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/var/run/php/php-fpm.sock;
    }

    location ~ /\\.ht {
        deny all;
    }

    location / {
        try_files $uri $uri/ /index.php?$args;
    }
}"""

    config_path = Path("/etc/nginx/sites-available/webmail")
    enabled_path = Path("/etc/nginx/sites-enabled/webmail")

    if utils.is_linux():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(nginx_config)
        if not enabled_path.exists():
            enabled_path.symlink_to(str(config_path))
        utils.run_command(["nginx", "-t"], check=False)
        utils.service_action("reload", "nginx")

    return {"status": "installed", "provider": "roundcube"}


def _uninstall_roundcube() -> dict:
    if not utils.is_linux():
        return {"status": "error", "message": "Uninstallation only supported on Linux"}

    utils.run_command(["apt-get", "remove", "-y", "roundcube"], check=False)

    enabled_path = Path("/etc/nginx/sites-enabled/webmail")
    config_path = Path("/etc/nginx/sites-available/webmail")

    if enabled_path.exists():
        enabled_path.unlink()
    if config_path.exists():
        config_path.unlink()

    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")

    return {"status": "uninstalled"}


def _generate_roundcube_config(domain: str) -> str:
    secret_key = secrets.token_hex(32)
    return f"""<?php
$config = [];
$config['db_dsnw'] = 'sqlite:///' . __DIR__ . '/db/roundcube.sqlite?mode=0646';
$config['default_host'] = 'ssl://mail.{domain}';
$config['default_port'] = 993;
$config['smtp_server'] = 'tls://mail.{domain}';
$config['smtp_port'] = 587;
$config['smtp_user'] = '%u';
$config['smtp_pass'] = '%p';
$config['des_key'] = '{secret_key}';
$config['skin'] = 'elastic';
$config['upload_max_size'] = 25M;
$config['max_message_size'] = 50M;
$config['enable_installer'] = false;
$config['log_dir'] = '/var/log/roundcube/';
$config['temp_dir'] = '/tmp/roundcube-tmp/';
$config['plugins'] = ['archive', 'zipdownload', 'password', 'jqueryui', 'archive'];
$config['password_charset'] = 'UTF-8';
return $config;
"""


@router.get("/status")
def webmail_status(user: dict = Depends(get_current_user)):
    config = _load_config()

    is_installed = False
    if utils.is_linux():
        result = utils.run_command(["dpkg", "-l", "roundcube"], check=False)
        is_installed = result and hasattr(result, 'returncode') and result.returncode == 0

    return {
        "enabled": config.get("enabled", False),
        "installed": is_installed,
        "provider": config.get("provider", "roundcube"),
        "skin": config.get("skin", "elastic"),
    }


@router.get("/config")
def get_config(user: dict = Depends(get_current_user)):
    return _load_config()


@router.post("/config")
def update_config(body: WebmailConfig, user: dict = Depends(get_current_user)):
    config = _load_config()
    if body.enabled is not None:
        if body.enabled and not config.get("enabled"):
            install_result = _install_roundcube()
            if install_result.get("status") == "error":
                return install_result
        elif not body.enabled and config.get("enabled"):
            _uninstall_roundcube()

        config["enabled"] = body.enabled
    if body.skin:
        config["skin"] = body.skin
    if body.upload_max_size:
        config["upload_max_size"] = body.upload_max_size

    _save_config(config)
    return {"status": "updated", "config": config}


@router.get("/login-url")
def get_login_url(user: dict = Depends(get_current_user)):
    config = _load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Webmail is not enabled")

    token = secrets.token_urlsafe(32)
    return {
        "url": "/webmail/",
        "token": token,
        "provider": config.get("provider", "roundcube"),
    }


@router.post("/configure/{domain}")
def configure_for_domain(domain: str, user: dict = Depends(get_current_user)):
    config = _load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Webmail is not enabled")

    if utils.is_linux():
        rc_config = _generate_roundcube_config(domain)
        config_dir = Path(f"/var/lib/roundcube/config/{domain}")
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.inc.php").write_text(rc_config)
        utils.run_command(["chown", "-R", "www-data:www-data", str(config_dir)], check=False)

    return {"status": "configured", "domain": domain}


@router.get("/accounts")
def list_accounts(user: dict = Depends(get_current_user)):
    email_file = utils.CONFIG_DIR / "email.json"
    if email_file.exists():
        email_data = json.loads(email_file.read_text())
        accounts = email_data.get("accounts", {})
        return {
            "accounts": [
                {"email": addr, "display_name": info.get("display_name", addr.split("@")[0])}
                for addr, info in accounts.items()
            ]
        }
    return {"accounts": []}
