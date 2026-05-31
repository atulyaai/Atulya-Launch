"""Plugin system API — discover, enable, disable plugins."""

import datetime
import importlib
import importlib.util
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

PLUGINS_FILE = utils.CONFIG_DIR / "plugins.json"
PLUGINS_DIR = utils.CONFIG_DIR / "plugins"


def _load_plugins() -> dict:
    if PLUGINS_FILE.exists():
        import json
        return json.loads(PLUGINS_FILE.read_text())
    return {"installed": {}, "enabled": {}}


def _save_plugins(data: dict):
    PLUGINS_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    PLUGINS_FILE.write_text(json.dumps(data, indent=2))


BUILTIN_PLUGINS = {
    "letsencrypt": {
        "name": "Let's Encrypt",
        "description": "Free SSL certificates via Let's Encrypt",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "ssl",
    },
    "cloudflare-dns": {
        "name": "Cloudflare DNS",
        "description": "Cloudflare DNS zone management",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "dns",
    },
    "redis-cache": {
        "name": "Redis Cache",
        "description": "Redis object caching for web apps",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "caching",
    },
    "modsecurity": {
        "name": "ModSecurity WAF",
        "description": "Web Application Firewall via ModSecurity",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "security",
    },
    "fail2ban": {
        "name": "Fail2Ban",
        "description": "Intrusion prevention with Fail2Ban",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "security",
    },
    "php-manager": {
        "name": "PHP Version Manager",
        "description": "Switch PHP versions per site",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "php",
    },
    "docker": {
        "name": "Docker Manager",
        "description": "Docker container and compose management",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "containers",
    },
    "git-deploy": {
        "name": "Git Deploy",
        "description": "Deploy sites from Git repositories",
        "version": "1.0.0",
        "author": "Atulya-Launch",
        "builtin": True,
        "category": "deployment",
    },
}


def _discover_user_plugins() -> dict:
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    discovered = {}
    for item in PLUGINS_DIR.iterdir():
        if item.is_dir() and (item / "manifest.json").exists():
            import json
            manifest = json.loads((item / "manifest.json").read_text())
            discovered[manifest.get("name", item.name)] = {
                "name": manifest.get("name", item.name),
                "description": manifest.get("description", ""),
                "version": manifest.get("version", "0.0.1"),
                "author": manifest.get("author", "Unknown"),
                "builtin": False,
                "category": manifest.get("category", "general"),
                "path": str(item),
            }
    return discovered


@router.get("")
def list_plugins(user: dict = Depends(get_current_user)):
    data = _load_plugins()
    user_plugins = _discover_user_plugins()
    all_plugins = {**BUILTIN_PLUGINS, **user_plugins}
    enabled = data.get("enabled", {})
    installed = data.get("installed", {})
    result = []
    for name, info in all_plugins.items():
        result.append({
            **info,
            "enabled": name in enabled,
            "installed": name in installed or info.get("builtin", False),
        })
    return {"plugins": result}


@router.get("/installed")
def installed_plugins(user: dict = Depends(get_current_user)):
    data = _load_plugins()
    enabled = data.get("enabled", {})
    installed = data.get("installed", {})
    all_plugins = {**BUILTIN_PLUGINS, **_discover_user_plugins()}
    result = []
    for name in set(list(installed.keys()) + list(enabled.keys())):
        if name in all_plugins:
            result.append({
                **all_plugins[name],
                "enabled": name in enabled,
                "installed": True,
            })
    return {"plugins": result}


@router.post("/{name}/enable")
def enable_plugin(name: str, user: dict = Depends(get_current_user)):
    all_plugins = {**BUILTIN_PLUGINS, **_discover_user_plugins()}
    if name not in all_plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    data = _load_plugins()
    data.setdefault("enabled", {})[name] = {
        "enabled_at": datetime.datetime.now().isoformat(),
        "enabled_by": user.get("sub", "admin"),
    }
    data.setdefault("installed", {})[name] = True
    _save_plugins(data)
    return {"status": "enabled", "plugin": name}


@router.post("/{name}/disable")
def disable_plugin(name: str, user: dict = Depends(get_current_user)):
    data = _load_plugins()
    enabled = data.get("enabled", {})
    if name not in enabled:
        raise HTTPException(status_code=404, detail="Plugin is not enabled")
    del enabled[name]
    _save_plugins(data)
    return {"status": "disabled", "plugin": name}


@router.post("/{name}/install")
def install_plugin(name: str, user: dict = Depends(get_current_user)):
    all_plugins = {**BUILTIN_PLUGINS, **_discover_user_plugins()}
    if name not in all_plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    data = _load_plugins()
    data.setdefault("installed", {})[name] = {
        "installed_at": datetime.datetime.now().isoformat(),
        "installed_by": user.get("sub", "admin"),
    }
    _save_plugins(data)
    return {"status": "installed", "plugin": name}
