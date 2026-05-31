"""PHP version management API."""

import os
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/php", tags=["php"])


def _get_available_versions() -> list:
    versions = []
    if utils.is_linux():
        result = utils.run_command(["update-alternatives", "--list", "php"], check=False)
        if result and result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                ver = line.split("/")[-1] if "/" in line else line
                versions.append({"path": line.strip(), "version": ver})
        else:
            for v in ["8.1", "8.2", "8.3"]:
                result2 = utils.run_command(["which", f"php{v}"], check=False)
                if result2 and result2.returncode == 0:
                    versions.append({"path": result2.stdout.strip(), "version": v})
    else:
        for v in ["8.1", "8.2", "8.3"]:
            versions.append({"path": f"/usr/bin/php{v}", "version": v})
    return versions


def _get_php_config_path(domain: str) -> str:
    return f"/etc/php/{domain}/fpm/pool.d/{domain}.conf"


def _get_php_ini_path(domain: str, version: str = "8.1") -> str:
    if utils.is_linux():
        return f"/etc/php/{version}/fpm/php.ini"
    return f"/etc/php{version}/php.ini"


@router.get("/versions")
def list_versions(user: dict = Depends(get_current_user)):
    versions = _get_available_versions()
    current = "unknown"
    if utils.is_linux():
        result = utils.run_command(["php", "-v"], check=False)
        if result and result.returncode == 0:
            match = re.search(r"PHP (\d+\.\d+)", result.stdout)
            if match:
                current = match.group(1)
    return {"versions": versions, "current": current}


@router.get("/config/{domain}")
def get_php_config(domain: str, user: dict = Depends(get_current_user)):
    config_data = utils.load_config()
    php_config = config_data.get("php", {}).get(domain, {})
    if not php_config:
        php_config = {"version": "8.1", "memory_limit": "256M", "upload_max_filesize": "64M", "post_max_size": "64M"}
    return {"domain": domain, "config": php_config}


@router.put("/config/{domain}")
def set_php_version(domain: str, body: dict, user: dict = Depends(get_current_user)):
    version = body.get("version", "8.1")
    all_config = utils.load_config()
    php_cfg = all_config.get("php", {})
    php_cfg[domain] = php_cfg.get(domain, {})
    php_cfg[domain]["version"] = version
    all_config["php"] = php_cfg
    utils.save_config(all_config)
    # Update FPM pool if Linux
    if utils.is_linux():
        pool_conf = f"/etc/php/{version}/fpm/pool.d/{domain}.conf"
        utils.run_command(["mkdir", "-p", os.path.dirname(pool_conf)], check=False)
        conf_content = (
            f"[{domain}]\n"
            f"user = www-data\n"
            f"group = www-data\n"
            f"listen = /run/php/php{version}-fpm-{domain}.sock\n"
            f"listen.owner = www-data\n"
            f"listen.group = www-data\n"
            f"pm = dynamic\n"
            f"pm.max_children = 10\n"
            f"pm.start_servers = 2\n"
            f"pm.min_spare_servers = 1\n"
            f"pm.max_spare_servers = 5\n"
        )
        utils.run_command(
            ["bash", "-c", f"cat > {pool_conf} << 'PHP_EOF'\n{conf_content}PHP_EOF"],
            check=False,
        )
        utils.run_command(["systemctl", "restart", f"php{version}-fpm"], check=False)
    return {"status": "updated", "domain": domain, "version": version}


@router.get("/settings/{domain}")
def get_php_settings(domain: str, user: dict = Depends(get_current_user)):
    config_data = utils.load_config()
    php_cfg = config_data.get("php", {}).get(domain, {})
    settings = {
        "memory_limit": php_cfg.get("memory_limit", "256M"),
        "upload_max_filesize": php_cfg.get("upload_max_filesize", "64M"),
        "post_max_size": php_cfg.get("post_max_size", "64M"),
        "max_execution_time": php_cfg.get("max_execution_time", "30"),
        "error_reporting": php_cfg.get("error_reporting", "E_ALL"),
        "display_errors": php_cfg.get("display_errors", "Off"),
        "log_errors": php_cfg.get("log_errors", "On"),
        "date.timezone": php_cfg.get("date.timezone", "UTC"),
    }
    return {"domain": domain, "settings": settings}


@router.put("/settings/{domain}")
def update_php_settings(domain: str, body: dict, user: dict = Depends(get_current_user)):
    all_config = utils.load_config()
    php_cfg = all_config.get("php", {})
    if domain not in php_cfg:
        php_cfg[domain] = {"version": "8.1"}
    for key, value in body.items():
        php_cfg[domain][key] = value
    all_config["php"] = php_cfg
    utils.save_config(all_config)
    # Write php.ini overrides if Linux
    if utils.is_linux():
        version = php_cfg[domain].get("version", "8.1")
        ini_dir = f"/etc/php/{version}/fpm/conf.d"
        utils.run_command(["mkdir", "-p", ini_dir], check=False)
        ini_content = "; Atulya-Launch custom settings for {domain}\n"
        for key, value in body.items():
            ini_content += f"{key} = {value}\n"
        ini_file = f"{ini_dir}/99-atulya-{domain}.ini"
        utils.run_command(
            ["bash", "-c", f"cat > {ini_file} << 'INI_EOF'\n{ini_content}INI_EOF"],
            check=False,
        )
        utils.run_command(["systemctl", "restart", f"php{version}-fpm"], check=False)
    return {"status": "settings updated", "domain": domain}
