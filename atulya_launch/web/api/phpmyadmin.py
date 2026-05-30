"""phpMyAdmin installation and management API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/phpmyadmin", tags=["phpmyadmin"])

PHPMYADMIN_FILE = utils.CONFIG_DIR / "phpmyadmin.json"
PHPMYADMIN_DIR = "/usr/share/phpmyadmin"
PHPMYADMIN_WEB_DIR = "/var/www/phpmyadmin"


def _load_config() -> dict:
    if PHPMYADMIN_FILE.exists():
        with open(PHPMYADMIN_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PHPMYADMIN_FILE, "w") as f:
        json.dump(data, f, indent=2)


class PhpMyAdminInstallRequest(BaseModel):
    version: Optional[str] = None
    install_path: Optional[str] = None
    enable_https: bool = False
    blowfish_secret: Optional[str] = None


def _is_installed() -> bool:
    return (PHPMYADMIN_DIR / "index.php").exists() or (PHPMYADMIN_WEB_DIR / "index.php").exists()


def _get_version() -> Optional[str]:
    if not _is_installed():
        return None
    config = _load_config()
    return config.get("version", "unknown")


def _create_nginx_config():
    nginx_config = """server {
    listen 80;
    server_name _;
    root /var/www/phpmyadmin;
    index index.php index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location ~ \\.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/var/run/php/php8.1-fpm.sock;
    }

    location ~ /\\. {
        deny all;
    }
}"""
    config_path = "/etc/nginx/sites-available/phpmyadmin"
    enabled_path = "/etc/nginx/sites-enabled/phpmyadmin"

    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        f.write(nginx_config)

    import os
    if not os.path.exists(enabled_path):
        os.symlink(config_path, enabled_path)

    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")


@router.get("/status")
def get_status(user: dict = Depends(get_current_user)):
    installed = _is_installed()
    version = _get_version()
    config = _load_config()

    status = {
        "installed": installed,
        "version": version,
        "install_path": config.get("install_path", PHPMYADMIN_DIR if installed else None),
        "blowfish_secret_set": bool(config.get("blowfish_secret")),
        "url": config.get("url", "/phpmyadmin" if installed else None),
    }

    if installed:
        result = utils.run_command(["php", "-r", "echo phpversion();"], check=False)
        if result and result.returncode == 0:
            status["php_version"] = result.stdout.strip()

    return status


@router.post("/install")
def install_phpmyadmin(body: PhpMyAdminInstallRequest, user: dict = Depends(get_current_user)):
    if _is_installed():
        raise HTTPException(status_code=409, detail="phpMyAdmin is already installed")

    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="phpMyAdmin installation is only supported on Linux")

    install_path = body.install_path or PHPMYADMIN_DIR
    version = body.version or "latest"
    blowfish_secret = body.blowfish_secret or utils.generate_password(32)

    result = utils.run_command(["apt-get", "install", "-y", "phpmyadmin"], check=False, timeout=300)
    if result and result.returncode != 0:
        import tempfile
        import urllib.request

        download_dir = tempfile.mkdtemp(prefix="phpmyadmin_")
        url = f"https://files.phpmyadmin.net/phpMyAdmin/{version}/phpMyAdmin-{version}-all-languages.tar.gz"
        try:
            tar_path = f"{download_dir}/phpmyadmin.tar.gz"
            urllib.request.urlretrieve(url, tar_path)
            utils.run_command(["tar", "-xzf", tar_path, "-C", "/usr/share/"], check=False)
            extracted_dir = f"/usr/share/phpMyAdmin-{version}-all-languages"
            utils.run_command(["mv", extracted_dir, install_path], check=False)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Download failed: {e}")
        finally:
            import shutil
            shutil.rmtree(download_dir, ignore_errors=True)

    config_inc = f"""<?php
$cfg['blowfish_secret'] = '{blowfish_secret}';
$cfg['Servers'][$i]['auth_type'] = 'cookie';
$cfg['Servers'][$i]['host'] = 'localhost';
$cfg['Servers'][$i]['compress'] = false;
$cfg['Servers']['AllowNoPassword'] = false;
$cfg['UploadDir'] = '';
$cfg['SaveDir'] = '';
$cfg['TempDir'] = '/tmp';
"""
    config_dir = f"{install_path}/config"
    import os
    os.makedirs(config_dir, exist_ok=True)
    with open(f"{config_dir}/config.inc.php", "w") as f:
        f.write(config_inc)

    _create_nginx_config()

    config_data = {
        "installed": True,
        "version": version,
        "install_path": install_path,
        "blowfish_secret": blowfish_secret,
        "url": "/phpmyadmin",
        "installed_at": __import__("datetime").datetime.now().isoformat(),
    }
    _save_config(config_data)

    return {"status": "installed", "version": version, "url": "/phpmyadmin"}


@router.get("/url")
def get_phpmyadmin_url(user: dict = Depends(get_current_user)):
    if not _is_installed():
        raise HTTPException(status_code=404, detail="phpMyAdmin is not installed")
    config = _load_config()
    return {"url": config.get("url", "/phpmyadmin")}


@router.post("/uninstall")
def uninstall_phpmyadmin(user: dict = Depends(get_current_user)):
    if not _is_installed():
        raise HTTPException(status_code=404, detail="phpMyAdmin is not installed")

    import shutil
    install_dir = _load_config().get("install_path", PHPMYADMIN_DIR)
    if (PHPMYADMIN_DIR).exists():
        shutil.rmtree(str(PHPMYADMIN_DIR))
    if (PHPMYADMIN_WEB_DIR).exists():
        shutil.rmtree(str(PHPMYADMIN_WEB_DIR))

    utils.run_command(["rm", "-f", "/etc/nginx/sites-available/phpmyadmin"], check=False)
    utils.run_command(["rm", "-f", "/etc/nginx/sites-enabled/phpmyadmin"], check=False)
    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")

    _save_config({})

    return {"status": "uninstalled"}
