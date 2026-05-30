"""NGINX FastCGI / proxy cache management API."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/nginx/cache", tags=["nginx-cache"])

NGINX_CACHE_FILE = utils.CONFIG_DIR / "nginx_cache.json"
CACHE_PATH = "/var/cache/nginx"


class CacheConfig(BaseModel):
    path: str = CACHE_PATH
    max_size: str = "1g"
    levels: str = "1:2"
    inactive: str = "60m"
    keys_zone: str = "default_cache:10m"


def _load_cache_conf() -> dict:
    if NGINX_CACHE_FILE.exists():
        import json
        return json.loads(NGINX_CACHE_FILE.read_text())
    return {"enabled": False, "config": {}, "purge_history": []}


def _save_cache_conf(data: dict):
    NGINX_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    NGINX_CACHE_FILE.write_text(json.dumps(data, indent=2))


def _nginx_conf_path() -> str:
    return "/etc/nginx/nginx.conf"


def _cache_conf_snippet() -> str:
    return "/etc/nginx/snippets/cache.conf"


def _generate_cache_block(config: CacheConfig) -> str:
    return (
        f"proxy_cache_path {config.path} levels={config.levels} "
        f"keys_zone={config.keys_zone} max_size={config.max_size} "
        f"inactive={config.inactive} use_temp_path=off;\n\n"
        f"fastcgi_cache_path {config.path}/fastcgi levels={config.levels} "
        f"keys_zone=fastcgi_cache:10m max_size={config.max_size} "
        f"inactive={config.inactive};\n"
    )


def _get_sites_with_cache() -> list:
    result = utils.run_command(["grep", "-rl", "proxy_cache", "/etc/nginx/sites-enabled/"], check=False)
    if not result or result.returncode != 0:
        return []
    return [p.split("/")[-1] for p in result.stdout.strip().splitlines() if p]


@router.get("/status")
def get_status(user: dict = Depends(get_current_user)):
    data = _load_cache_conf()
    nginx_running = utils.service_exists("nginx")
    cache_files = 0
    cache_size = 0
    cache_dir = Path(CACHE_PATH)
    if cache_dir.exists():
        cache_files = sum(1 for _ in cache_dir.rglob("*") if _.is_file())
        cache_size = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
    return {
        "enabled": data.get("enabled", False),
        "nginx_running": nginx_running,
        "cached_sites": _get_sites_with_cache(),
        "cache_files": cache_files,
        "cache_size_bytes": cache_size,
        "cache_path": CACHE_PATH,
    }


@router.post("/enable")
def enable_cache(body: CacheConfig, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="NGINX cache management is only supported on Linux")
    snippet = Path(_cache_conf_snippet())
    snippet.parent.mkdir(parents=True, exist_ok=True)
    snippet.write_text(_generate_cache_block(body))
    Path(body.path).mkdir(parents=True, exist_ok=True)
    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")
    data = _load_cache_conf()
    data["enabled"] = True
    data["config"] = body.dict()
    data["enabled_at"] = datetime.datetime.now().isoformat()
    _save_cache_conf(data)
    return {"status": "enabled", "path": body.path}


@router.post("/disable")
def disable_cache(user: dict = Depends(get_current_user)):
    snippet = Path(_cache_conf_snippet())
    if snippet.exists():
        snippet.unlink()
    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")
    data = _load_cache_conf()
    data["enabled"] = False
    _save_cache_conf(data)
    return {"status": "disabled"}


@router.post("/purge/{domain}")
def purge_domain_cache(domain: str, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Cache purge is only supported on Linux")
    cache_dir = Path(CACHE_PATH)
    purged = 0
    if cache_dir.exists():
        for f in cache_dir.rglob(f"*{domain}*"):
            if f.is_file():
                f.unlink()
                purged += 1
    data = _load_cache_conf()
    data.setdefault("purge_history", []).append({
        "domain": domain,
        "files_purged": purged,
        "timestamp": datetime.datetime.now().isoformat(),
    })
    _save_cache_conf(data)
    return {"status": "purged", "domain": domain, "files_purged": purged}


@router.get("/stats")
def cache_stats(user: dict = Depends(get_current_user)):
    data = _load_cache_conf()
    purge_history = data.get("purge_history", [])
    cache_dir = Path(CACHE_PATH)
    total_files = 0
    total_size = 0
    by_extension = {}
    if cache_dir.exists():
        for f in cache_dir.rglob("*"):
            if f.is_file():
                total_files += 1
                total_size += f.stat().st_size
                ext = f.suffix or "no_ext"
                by_extension[ext] = by_extension.get(ext, 0) + 1
    return {
        "total_files": total_files,
        "total_size_bytes": total_size,
        "by_extension": by_extension,
        "purge_history": purge_history[-20:],
        "enabled": data.get("enabled", False),
    }


from pathlib import Path
