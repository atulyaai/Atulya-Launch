"""One-click app installer API."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/apps", tags=["apps"])

AVAILABLE_APPS = {
    "wordpress": {
        "name": "WordPress",
        "description": "Popular CMS and blogging platform",
        "version": "6.5",
        "category": "cms",
        "requires": ["php", "mysql"],
        "install_cmd": "wp core install --allow-root",
    },
    "ghost": {
        "name": "Ghost",
        "description": "Professional publishing platform",
        "version": "5.75",
        "category": "cms",
        "requires": ["nodejs", "mysql"],
        "install_cmd": "ghost install",
    },
    "nextcloud": {
        "name": "Nextcloud",
        "description": "Self-hosted productivity platform",
        "version": "29.0",
        "category": "productivity",
        "requires": ["php", "mysql"],
    },
    "gitea": {
        "name": "Gitea",
        "description": "Lightweight Git hosting",
        "version": "1.22",
        "category": "development",
        "requires": ["git"],
    },
    "minio": {
        "name": "MinIO",
        "description": "S3-compatible object storage",
        "version": "latest",
        "category": "storage",
        "requires": [],
    },
    "n8n": {
        "name": "n8n",
        "description": "Workflow automation",
        "version": "1.40",
        "category": "automation",
        "requires": ["nodejs"],
    },
    "uptimekuma": {
        "name": "Uptime Kuma",
        "description": "Monitoring tool",
        "version": "1.23",
        "category": "monitoring",
        "requires": ["nodejs"],
    },
    "vaultwarden": {
        "name": "Vaultwarden",
        "description": "Bitwarden-compatible password manager",
        "version": "1.30",
        "category": "security",
        "requires": [],
    },
}


def _installed_apps() -> dict:
    p = utils.CONFIG_DIR / "apps.json"
    if not p.exists():
        return {}
    import json
    return json.loads(p.read_text())


def _save_installed(apps: dict):
    p = utils.CONFIG_DIR / "apps.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(apps, indent=2))


@router.get("/available")
def list_available(user: dict = Depends(get_current_user)):
    installed = _installed_apps()
    result = []
    for slug, info in AVAILABLE_APPS.items():
        entry = {**info, "slug": slug, "installed": slug in installed}
        result.append(entry)
    return {"apps": result}


@router.get("/installed")
def list_installed(user: dict = Depends(get_current_user)):
    return {"apps": _installed_apps()}


class InstallRequest(BaseModel):
    slug: str
    domain: Optional[str] = None
    database: Optional[str] = None


@router.post("/install")
def install_app(body: InstallRequest, user: dict = Depends(get_current_user)):
    if body.slug not in AVAILABLE_APPS:
        raise HTTPException(status_code=404, detail="App not found")
    installed = _installed_apps()
    if body.slug in installed:
        raise HTTPException(status_code=409, detail="App already installed")
    info = AVAILABLE_APPS[body.slug]
    app_record = {
        "slug": body.slug,
        "name": info["name"],
        "version": info["version"],
        "domain": body.domain,
        "database": body.database,
        "installed_at": datetime.datetime.now().isoformat(),
        "status": "installed",
    }
    installed[body.slug] = app_record
    _save_installed(installed)
    return {"status": "installed", "app": app_record}


@router.delete("/{name}")
def uninstall_app(name: str, user: dict = Depends(get_current_user)):
    installed = _installed_apps()
    if name not in installed:
        raise HTTPException(status_code=404, detail="App not installed")
    del installed[name]
    _save_installed(installed)
    return {"status": "uninstalled", "name": name}


@router.post("/{name}/update")
def update_app(name: str, user: dict = Depends(get_current_user)):
    installed = _installed_apps()
    if name not in installed:
        raise HTTPException(status_code=404, detail="App not installed")
    if name in AVAILABLE_APPS:
        installed[name]["version"] = AVAILABLE_APPS[name]["version"]
        installed[name]["updated_at"] = datetime.datetime.now().isoformat()
        _save_installed(installed)
    return {"status": "updated", "name": name}
