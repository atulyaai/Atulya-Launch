"""OpenLiteSpeed Integration API."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/litespeed", tags=["litespeed"])

OLS_CONFIG_DIR = Path("/usr/local/lsws")
OLS_CONF = OLS_CONFIG_DIR / "conf" / "httpd.conf"
CACHE_CONFIG_FILE = utils.CONFIG_DIR / "litespeed_cache.json"


def _ols_installed() -> bool:
    return (OLS_CONFIG_DIR / "bin" / "lswsctrl").exists() or shutil.which("lswsctrl") is not None


def _ols_running() -> bool:
    result = utils.run_command(["pgrep", "-x", "litespeed"], check=False)
    return result is not None and result.returncode == 0


def _load_cache_config() -> dict:
    if CACHE_CONFIG_FILE.exists():
        with open(CACHE_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_cache_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_ols_status() -> dict:
    installed = _ols_installed()
    running = _ols_running()

    version = ""
    if installed:
        result = utils.run_command(["lswsctrl", "-v"], check=False)
        if result and result.returncode == 0:
            version = result.stdout.strip()

    config_exists = OLS_CONF.exists()
    return {
        "installed": installed,
        "running": running,
        "version": version,
        "config_exists": config_exists,
        "config_dir": str(OLS_CONFIG_DIR),
    }


def _purge_ols_cache(domain: Optional[str] = None) -> dict:
    cache_root = OLS_CONFIG_DIR / "cache"
    if not cache_root.exists():
        cache_root = Path("/tmp/lsws-cache")

    if domain:
        domain_cache = cache_root / domain
        if domain_cache.exists():
            import shutil as sh
            sh.rmtree(domain_cache)
            return {"status": "purged", "domain": domain, "path": str(domain_cache)}
        return {"status": "not_found", "domain": domain}

    if cache_root.exists():
        import shutil as sh
        sh.rmtree(cache_root)
        cache_root.mkdir(parents=True, exist_ok=True)
        return {"status": "purged_all", "path": str(cache_root)}

    return {"status": "no_cache_found"}


class OLSInstall(BaseModel):
    port: int = 80
    admin_port: int = 7080
    admin_user: str = "admin"
    admin_password: Optional[str] = None


class CachePurge(BaseModel):
    domain: Optional[str] = None


@router.get("/status")
def litespeed_status(user: dict = Depends(get_current_user)):
    return _get_ols_status()


@router.post("/install")
def install_litespeed(body: OLSInstall, user: dict = Depends(get_current_user)):
    if _ols_installed():
        raise HTTPException(status_code=400, detail="OpenLiteSpeed is already installed")

    install_script = """#!/bin/bash
set -e
echo 'deb https://repo.litespeedrepo.com/debian stable main' > /etc/apt/sources.list.d/lst_repo.list
wget -qO - https://repo.litespeedrepo.com/debian/lst_debian_repo.key | apt-key add -
apt-get update -qq
apt-get install -y openlitespeed
"""
    result = utils.run_command(["bash", "-c", install_script], check=False, timeout=300)
    if not result or result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to install OpenLiteSpeed")

    password = body.admin_password or utils.generate_password(16)
    utils.run_command(
        ["lswsctrl", "passwd", body.admin_user, password],
        check=False,
    )

    if body.port != 80:
        httpd_conf = OLS_CONF
        if httpd_conf.exists():
            content = httpd_conf.read_text()
            content = content.replace("port 80", f"port {body.port}")
            httpd_conf.write_text(content)

    utils.run_command(["systemctl", "enable", "lsws"], check=False)
    utils.run_command(["systemctl", "start", "lsws"], check=False)

    return {
        "status": "installed",
        "admin_user": body.admin_user,
        "admin_password": password,
        "admin_url": f"http://localhost:{body.admin_port}",
    }


@router.post("/start")
def start_litespeed(user: dict = Depends(get_current_user)):
    result = utils.service_action("start", "lsws")
    return {"status": "started"}


@router.post("/stop")
def stop_litespeed(user: dict = Depends(get_current_user)):
    result = utils.service_action("stop", "lsws")
    return {"status": "stopped"}


@router.post("/restart")
def restart_litespeed(user: dict = Depends(get_current_user)):
    result = utils.run_command(["lswsctrl", "restart"], check=False)
    return {"status": "restarted"}


@router.get("/cache/purge")
def get_cache_info(user: dict = Depends(get_current_user)):
    config = _load_cache_config()
    cache_root = OLS_CONFIG_DIR / "cache"
    cache_size = 0
    cache_files = 0
    if cache_root.exists():
        for f in cache_root.rglob("*"):
            if f.is_file():
                cache_size += f.stat().st_size
                cache_files += 1
    return {
        "cache_root": str(cache_root),
        "cache_exists": cache_root.exists(),
        "cache_size_bytes": cache_size,
        "cache_files": cache_files,
        "config": config,
    }


@router.post("/cache/purge/{domain}")
def purge_cache_for_domain(domain: str, user: dict = Depends(get_current_user)):
    result = _purge_ols_cache(domain)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"No cache found for domain: {domain}")
    return result


@router.post("/cache/purge/all")
def purge_all_cache(user: dict = Depends(get_current_user)):
    result = _purge_ols_cache()
    return result
