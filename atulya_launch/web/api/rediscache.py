"""Redis / Memcached cache management API."""

import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/cache", tags=["cache"])

CACHE_FILE = utils.CONFIG_DIR / "cache.json"


class RedisConfig(BaseModel):
    port: int = 6379
    maxmemory: str = "256mb"
    maxmemory_policy: str = "allkeys-lru"
    password: Optional[str] = None
    bind: str = "127.0.0.1"


class MemcachedConfig(BaseModel):
    port: int = 11211
    maxmemory: str = "128m"
    threads: int = 4
    bind: str = "127.0.0.1"


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        import json
        return json.loads(CACHE_FILE.read_text())
    return {"redis": {"enabled": False}, "memcached": {"enabled": False}}


def _save_cache(data: dict):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    CACHE_FILE.write_text(json.dumps(data, indent=2))


def _redis_running() -> bool:
    result = utils.run_command(["redis-cli", "ping"], check=False)
    return result is not None and result.returncode == 0 and "PONG" in (result.stdout or "")


def _memcached_running() -> bool:
    result = utils.run_command(["pgrep", "-x", "memcached"], check=False)
    return result is not None and result.returncode == 0


def _redis_info() -> dict:
    result = utils.run_command(["redis-cli", "info"], check=False)
    if not result or result.returncode != 0:
        return {}
    info = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info


def _generate_redis_conf(config: RedisConfig) -> str:
    lines = [
        f"bind {config.bind}",
        f"port {config.port}",
        f"daemonize yes",
        f"pidfile /var/run/redis/redis-server.pid",
        f"logfile /var/log/redis/redis-server.log",
        f"maxmemory {config.maxmemory}",
        f"maxmemory-policy {config.maxmemory_policy}",
    ]
    if config.password:
        lines.append(f"requirepass {config.password}")
    return "\n".join(lines)


def _generate_memcached_conf(config: MemcachedConfig) -> str:
    return (
        f"-d -m {config.maxmemory.replace('m', '')} "
        f"-p {config.port} -l {config.bind} "
        f"-t {config.threads} "
        f"-u memcache"
    )


@router.get("/redis/status")
def redis_status(user: dict = Depends(get_current_user)):
    data = _load_cache()
    running = _redis_running()
    info = _redis_info() if running else {}
    return {
        "enabled": data.get("redis", {}).get("enabled", False),
        "running": running,
        "info": {
            "version": info.get("redis_version", ""),
            "used_memory": info.get("used_memory_human", ""),
            "connected_clients": info.get("connected_clients", ""),
            "total_commands": info.get("total_commands_processed", ""),
            "hits": info.get("keyspace_hits", ""),
            "misses": info.get("keyspace_misses", ""),
        },
    }


@router.post("/redis/enable")
def enable_redis(body: RedisConfig, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Redis management is only supported on Linux")
    conf_content = _generate_redis_conf(body)
    conf_path = Path("/etc/redis/redis.conf")
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    conf_path.write_text(conf_content)
    utils.service_action("start", "redis-server")
    data = _load_cache()
    data["redis"] = {"enabled": True, "config": body.dict(), "enabled_at": datetime.datetime.now().isoformat()}
    _save_cache(data)
    return {"status": "enabled", "port": body.port}


@router.post("/redis/disable")
def disable_redis(user: dict = Depends(get_current_user)):
    utils.service_action("stop", "redis-server")
    data = _load_cache()
    data["redis"]["enabled"] = False
    _save_cache(data)
    return {"status": "disabled"}


@router.get("/redis/info")
def redis_info(user: dict = Depends(get_current_user)):
    if not _redis_running():
        return {"error": "Redis is not running"}
    return {"info": _redis_info()}


@router.get("/memcached/status")
def memcached_status(user: dict = Depends(get_current_user)):
    data = _load_cache()
    running = _memcached_running()
    return {
        "enabled": data.get("memcached", {}).get("enabled", False),
        "running": running,
    }


@router.post("/memcached/enable")
def enable_memcached(body: MemcachedConfig, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Memcached management is only supported on Linux")
    args = _generate_memcached_conf(body)
    utils.run_command(f"memcached {args}", check=False)
    data = _load_cache()
    data["memcached"] = {"enabled": True, "config": body.dict(), "enabled_at": datetime.datetime.now().isoformat()}
    _save_cache(data)
    return {"status": "enabled", "port": body.port}


@router.post("/memcached/disable")
def disable_memcached(user: dict = Depends(get_current_user)):
    utils.run_command(["pkill", "memcached"], check=False)
    data = _load_cache()
    data["memcached"]["enabled"] = False
    _save_cache(data)
    return {"status": "disabled"}


from pathlib import Path
