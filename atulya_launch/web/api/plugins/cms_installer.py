"""One-Click CMS Installer - WordPress, Joomla, Drupal, Ghost, etc."""

import json
import shutil
import subprocess
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/installer", tags=["installer"])

INSTALL_DIR = utils.CONFIG_DIR / "installer"
MANIFEST_FILE = INSTALL_DIR / "manifest.json"
INSTALLED_FILE = INSTALL_DIR / "installed.json"

CMS_MANIFEST = [
    {
        "name": "wordpress",
        "title": "WordPress",
        "description": "Most popular CMS for blogs and websites",
        "version": "6.7",
        "icon": "wordpress",
        "color": "#21759b",
        "requires_db": True,
        "requires_php": "7.4",
        "size_mb": 65,
        "install_time_sec": 30,
        "url": "https://wordpress.org/latest.tar.gz",
    },
    {
        "name": "joomla",
        "title": "Joomla",
        "description": "Flexible CMS for portals and e-commerce",
        "version": "5.2",
        "icon": "joomla",
        "color": "#f44321",
        "requires_db": True,
        "requires_php": "8.1",
        "size_mb": 50,
        "install_time_sec": 45,
        "url": "https://downloads.joomla.org/cms/joomla5/5-2-0/Joomla_5.2.0-Stable-Full_Package.zip",
    },
    {
        "name": "drupal",
        "title": "Drupal",
        "description": "Enterprise-grade CMS for complex sites",
        "version": "11.1",
        "icon": "drupal",
        "color": "#0678be",
        "requires_db": True,
        "requires_php": "8.1",
        "size_mb": 55,
        "install_time_sec": 60,
        "url": "https://ftp.drupal.org/files/projects/drupal-11.1.0.tar.gz",
    },
    {
        "name": "ghost",
        "title": "Ghost",
        "description": "Modern publishing platform for newsletters and blogs",
        "version": "5.82",
        "icon": "ghost",
        "color": "#212121",
        "requires_db": False,
        "requires_node": True,
        "size_mb": 120,
        "install_time_sec": 90,
        "url": "https://ghost.org/zip/ghost.zip",
    },
    {
        "name": "laravel",
        "title": "Laravel",
        "description": "PHP web framework with artisan CLI",
        "version": "11.30",
        "icon": "laravel",
        "color": "#ff2d20",
        "requires_db": True,
        "requires_php": "8.2",
        "size_mb": 40,
        "install_time_sec": 45,
        "url": None,
        "composer_package": "laravel/laravel",
    },
    {
        "name": "nextcloud",
        "title": "Nextcloud",
        "description": "Self-hosted productivity platform (files, calendar, contacts)",
        "version": "30",
        "icon": "nextcloud",
        "color": "#0082c9",
        "requires_db": True,
        "requires_php": "8.1",
        "size_mb": 200,
        "install_time_sec": 120,
        "url": "https://download.nextcloud.com/server/releases/latest.tar.bz2",
    },
    {
        "name": "matomo",
        "title": "Matomo",
        "description": "Open-source web analytics (Google Analytics alternative)",
        "version": "5.2",
        "icon": "matomo",
        "color": "#2e7d32",
        "requires_db": True,
        "requires_php": "8.0",
        "size_mb": 80,
        "install_time_sec": 60,
        "url": "https://builds.matomo.org/matomo.zip",
    },
    {
        "name": "phpbb",
        "title": "phpBB",
        "description": "Forum software",
        "version": "3.3",
        "icon": "phpbb",
        "color": "#4b7bac",
        "requires_db": True,
        "requires_php": "7.4",
        "size_mb": 15,
        "install_time_sec": 20,
        "url": "https://www.phpbb.com/files/releases/phpBB-3.3.12.zip",
    },
]


class InstallRequest(BaseModel):
    cms: str
    domain: str
    path: str = ""
    admin_user: str = "admin"
    admin_password: str = ""
    admin_email: str = ""
    site_title: str = ""
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None


def _ensure_dirs():
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_FILE.exists():
        MANIFEST_FILE.write_text(json.dumps(CMS_MANIFEST, indent=2))
    if not INSTALLED_FILE.exists():
        INSTALLED_FILE.write_text(json.dumps([], indent=2))


def _load_installed() -> list:
    _ensure_dirs()
    return json.loads(INSTALLED_FILE.read_text())


def _save_installed(data: list):
    _ensure_dirs()
    INSTALLED_FILE.write_text(json.dumps(data, indent=2))


def _download_file(url: str, dest: Path):
    urllib.request.urlretrieve(url, str(dest))


def _generate_wp_config(db_name: str, db_user: str, db_password: str, site_title: str, admin_user: str, admin_password: str, admin_email: str) -> str:
    import secrets
    auth_key = secrets.token_hex(32)
    secure_auth = secrets.token_hex(32)
    logged_in = secrets.token_hex(32)
    nonce = secrets.token_hex(32)
    return f"""<?php
define('DB_NAME', '{db_name}');
define('DB_USER', '{db_user}');
define('DB_PASSWORD', '{db_password}');
define('DB_HOST', 'localhost');
define('DB_CHARSET', 'utf8mb4');
define('DB_COLLATE', 'utf8mb4_unicode_ci');

define('AUTH_KEY',         '{auth_key}');
define('SECURE_AUTH_KEY',  '{secure_auth}');
define('LOGGED_IN_KEY',    '{logged_in}');
define('NONCE_KEY',        '{nonce}');
define('AUTH_SALT',        '{secrets.token_hex(32)}');
define('SECURE_AUTH_SALT', '{secrets.token_hex(32)}');
define('LOGGED_IN_SALT',   '{secrets.token_hex(32)}');
define('NONCE_SALT',       '{secrets.token_hex(32)}');

$table_prefix = 'wp_';
define('WP_DEBUG', false);
define('WP_MEMORY_LIMIT', '256M');
define('WP_MAX_MEMORY_LIMIT', '512M');
define('DISALLOW_FILE_EDIT', true);

if (!defined('ABSPATH')) {{
    define('ABSPATH', __DIR__ . '/');
}}
require_once ABSPATH . 'wp-settings.php';
"""


def _install_wordpress(req: InstallRequest) -> dict:
    site_dir = Path(req.domain.replace("*.", ""))
    base = Path("/var/www") if utils.is_linux() else utils.CONFIG_DIR / "sites"
    install_path = base / site_dir / (req.path or "public_html")

    if utils.is_linux():
        install_path.mkdir(parents=True, exist_ok=True)
    else:
        install_path.mkdir(parents=True, exist_ok=True)

    wp_zip = INSTALL_DIR / "wordpress.tar.gz"
    _download_file("https://wordpress.org/latest.tar.gz", wp_zip)

    subprocess.run(
        ["tar", "-xzf", str(wp_zip), "-C", str(install_path), "--strip-components=1"],
        capture_output=True, check=False,
    )

    db_name = req.db_name or f"wp_{site_dir}".replace("-", "_")
    db_user = req.db_user or f"wp_{site_dir}".replace("-", "_")[:16]
    db_password = req.db_password or utils.generate_password(24)
    admin_password = req.admin_password or utils.generate_password(16)
    site_title = req.site_title or req.domain

    wp_config = _generate_wp_config(db_name, db_user, db_password, site_title, req.admin_user, admin_password, req.admin_email)
    (install_path / "wp-config.php").write_text(wp_config)

    if utils.is_linux():
        for wp_dir in ["wp-content/uploads", "wp-content/cache", "wp-content/plugins"]:
            (install_path / wp_dir).mkdir(parents=True, exist_ok=True)
            subprocess.run(["chmod", "-R", "755", str(install_path / wp_dir)], capture_output=True, check=False)
        subprocess.run(["chown", "-R", "www-data:www-data", str(install_path)], capture_output=True, check=False)

    wp_content = install_path / "wp-content"
    wp_content.mkdir(exist_ok=True)

    return {
        "status": "installed",
        "cms": "wordpress",
        "domain": req.domain,
        "path": req.path,
        "install_path": str(install_path),
        "admin_url": f"http://{req.domain}/{req.path}/wp-admin/",
        "admin_user": req.admin_user,
        "admin_password": admin_password,
        "admin_email": req.admin_email,
        "site_title": site_title,
        "database": {"name": db_name, "user": db_user, "password": db_password},
    }


def _install_joomla(req: InstallRequest) -> dict:
    site_dir = Path(req.domain.replace("*.", ""))
    install_path = Path("/var/www") / site_dir / (req.path or "public_html")
    install_path.mkdir(parents=True, exist_ok=True)

    joomla_zip = INSTALL_DIR / "joomla.zip"
    _download_file(
        "https://downloads.joomla.org/cms/joomla5/5-2-0/Joomla_5.2.0-Stable-Full_Package.zip",
        joomla_zip,
    )
    subprocess.run(
        ["unzip", "-o", str(joomla_zip), "-d", str(install_path)],
        capture_output=True, check=False,
    )

    db_name = req.db_name or f"joomla_{site_dir}".replace("-", "_")
    db_user = req.db_user or f"joomla_{site_dir}".replace("-", "_")[:16]
    db_password = req.db_password or utils.generate_password(24)
    admin_password = req.admin_password or utils.generate_password(16)

    if utils.is_linux():
        subprocess.run(["chown", "-R", "www-data:www-data", str(install_path)], capture_output=True, check=False)

    return {
        "status": "installed",
        "cms": "joomla",
        "domain": req.domain,
        "install_path": str(install_path),
        "admin_url": f"http://{req.domain}/{req.path}/administrator/",
        "admin_user": req.admin_user,
        "admin_password": admin_password,
        "database": {"name": db_name, "user": db_user, "password": db_password},
        "note": "Run the web installer at /administrator/ to complete setup",
    }


def _install_drupal(req: InstallRequest) -> dict:
    site_dir = Path(req.domain.replace("*.", ""))
    install_path = Path("/var/www") / site_dir / (req.path or "public_html")
    install_path.mkdir(parents=True, exist_ok=True)

    drupal_tar = INSTALL_DIR / "drupal.tar.gz"
    _download_file("https://ftp.drupal.org/files/projects/drupal-11.1.0.tar.gz", drupal_tar)
    subprocess.run(
        ["tar", "-xzf", str(drupal_tar), "-C", str(install_path), "--strip-components=1"],
        capture_output=True, check=False,
    )

    db_name = req.db_name or f"drupal_{site_dir}".replace("-", "_")
    db_user = req.db_user or f"drupal_{site_dir}".replace("-", "_")[:16]
    db_password = req.db_password or utils.generate_password(24)

    if utils.is_linux():
        subprocess.run(["chown", "-R", "www-data:www-data", str(install_path)], capture_output=True, check=False)

    return {
        "status": "installed",
        "cms": "drupal",
        "domain": req.domain,
        "install_path": str(install_path),
        "admin_url": f"http://{req.domain}/{req.path}/user/login",
        "database": {"name": db_name, "user": db_user, "password": db_password},
        "note": "Complete installation via the web installer",
    }


def _install_nextcloud(req: InstallRequest) -> dict:
    site_dir = Path(req.domain.replace("*.", ""))
    install_path = Path("/var/www") / site_dir / (req.path or "public_html")
    install_path.mkdir(parents=True, exist_ok=True)

    nc_tar = INSTALL_DIR / "nextcloud.tar.bz2"
    _download_file("https://download.nextcloud.com/server/releases/latest.tar.bz2", nc_tar)
    subprocess.run(
        ["tar", "-xjf", str(nc_tar), "-C", str(install_path), "--strip-components=1"],
        capture_output=True, check=False,
    )

    db_name = req.db_name or f"nextcloud_{site_dir}".replace("-", "_")
    db_user = req.db_user or f"nc_{site_dir}".replace("-", "_")[:16]
    db_password = req.db_password or utils.generate_password(24)
    admin_password = req.admin_password or utils.generate_password(16)

    if utils.is_linux():
        subprocess.run(["chown", "-R", "www-data:www-data", str(install_path)], capture_output=True, check=False)

    return {
        "status": "installed",
        "cms": "nextcloud",
        "domain": req.domain,
        "install_path": str(install_path),
        "admin_url": f"http://{req.domain}/{req.path}/",
        "admin_user": req.admin_user,
        "admin_password": admin_password,
        "database": {"name": db_name, "user": db_user, "password": db_password},
    }


def _install_ghost(req: InstallRequest) -> dict:
    site_dir = Path(req.domain.replace("*.", ""))
    install_path = Path("/opt/ghost") / site_dir
    install_path.mkdir(parents=True, exist_ok=True)

    admin_password = req.admin_password or utils.generate_password(16)

    if utils.is_linux():
        subprocess.run(
            ["bash", "-c", f"curl -sSL https://ghost.org/install.sh | bash -s -- --domain {req.domain} --dir {install_path}"],
            capture_output=True, check=False,
        )

    return {
        "status": "installed",
        "cms": "ghost",
        "domain": req.domain,
        "install_path": str(install_path),
        "admin_url": f"http://{req.domain}/ghost/",
        "admin_email": req.admin_email,
        "admin_password": admin_password,
    }


INSTALLERS = {
    "wordpress": _install_wordpress,
    "joomla": _install_joomla,
    "drupal": _install_drupal,
    "nextcloud": _install_nextcloud,
    "ghost": _install_ghost,
}


@router.get("/manifest")
def get_manifest(user: dict = Depends(get_current_user)):
    _ensure_dirs()
    return {"apps": CMS_MANIFEST}


@router.get("/installed")
def list_installed(user: dict = Depends(get_current_user)):
    return {"installed": _load_installed()}


@router.post("/install")
def install_app(body: InstallRequest, user: dict = Depends(get_current_user)):
    _ensure_dirs()
    installer = INSTALLERS.get(body.cms)
    if not installer:
        raise HTTPException(status_code=400, detail=f"Unknown CMS: {body.cms}")

    result = installer(body)

    record = {
        "cms": body.cms,
        "domain": body.domain,
        "path": body.path,
        "admin_url": result.get("admin_url"),
        "install_path": result.get("install_path"),
        "installed_at": datetime.now().isoformat(),
        "database": result.get("database"),
    }
    installed = _load_installed()
    installed.append(record)
    _save_installed(installed)

    return result


@router.post("/uninstall")
def uninstall_app(body: dict, user: dict = Depends(get_current_user)):
    domain = body.get("domain", "")
    cms = body.get("cms", "")
    installed = _load_installed()
    found = [i for i in installed if i["domain"] == domain and i["cms"] == cms]
    if not found:
        raise HTTPException(status_code=404, detail="App not found")

    install_path = Path(found[0].get("install_path", ""))
    if install_path.exists():
        shutil.rmtree(str(install_path), ignore_errors=True)

    installed = [i for i in installed if not (i["domain"] == domain and i["cms"] == cms)]
    _save_installed(installed)

    return {"status": "uninstalled", "cms": cms, "domain": domain}


@router.get("/stats")
def installer_stats(user: dict = Depends(get_current_user)):
    installed = _load_installed()
    by_cms = {}
    for app in installed:
        cms = app["cms"]
        by_cms[cms] = by_cms.get(cms, 0) + 1
    return {
        "total_installed": len(installed),
        "by_cms": by_cms,
        "available_apps": len(CMS_MANIFEST),
    }
