"""Bandwidth limiting API for sites."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/sites/{domain}/bandwidth-limit", tags=["bandwidth"])

BANDWIDTH_FILE = utils.CONFIG_DIR / "bandwidth.json"


class BandwidthConfig(BaseModel):
    monthly_limit_gb: float = 100.0
    alert_threshold_percent: float = 80.0
    enabled: bool = True
    block_on_exceed: bool = False
    current_usage_bytes: int = 0
    reset_day: int = 1


def _load_bandwidth() -> dict:
    if BANDWIDTH_FILE.exists():
        import json
        return json.loads(BANDWIDTH_FILE.read_text())
    return {"domains": {}}


def _save_bandwidth(data: dict):
    BANDWIDTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    BANDWIDTH_FILE.write_text(json.dumps(data, indent=2))


def _get_nginx_bandwidth_stats(domain: str) -> dict:
    awk_pattern = f"/server_name.*{domain}/,/^}}/"
    result = utils.run_command(
        ["awk", awk_pattern, "/var/log/nginx/access.log"],
        check=False,
    )
    total_bytes = 0
    request_count = 0
    if result and result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 10:
                try:
                    total_bytes += int(parts[9]) if parts[9] != "-" else 0
                    request_count += 1
                except (ValueError, IndexError):
                    pass
    return {"bytes": total_bytes, "requests": request_count}


def _generate_nginx_limit(zone_name: str, limit_mbps: int) -> str:
    return (
        f"# Bandwidth limit zone\n"
        f"limit_req_zone $binary_remote_addr zone={zone_name}:10m rate={limit_mbps}r/s;\n"
        f"limit_conn_zone $binary_remote_addr zone=conn_{zone_name}:10m;\n"
    )


def _bytes_to_human(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"


@router.get("")
def get_bandwidth(domain: str, user: dict = Depends(get_current_user)):
    data = _load_bandwidth()
    config = data.get("domains", {}).get(domain, {
        "monthly_limit_gb": 100.0,
        "alert_threshold_percent": 80.0,
        "enabled": False,
        "block_on_exceed": False,
        "current_usage_bytes": 0,
        "reset_day": 1,
    })
    usage_pct = 0
    limit_bytes = config.get("monthly_limit_gb", 100) * (1024 ** 3)
    if limit_bytes > 0:
        usage_pct = round((config.get("current_usage_bytes", 0) / limit_bytes) * 100, 2)
    return {
        "domain": domain,
        "bandwidth": {
            **config,
            "usage_percent": usage_pct,
            "limit_human": _bytes_to_human(limit_bytes),
            "usage_human": _bytes_to_human(config.get("current_usage_bytes", 0)),
            "remaining_human": _bytes_to_human(max(0, limit_bytes - config.get("current_usage_bytes", 0))),
        },
    }


@router.put("")
def set_bandwidth(domain: str, body: BandwidthConfig, user: dict = Depends(get_current_user)):
    if body.monthly_limit_gb <= 0:
        raise HTTPException(status_code=400, detail="monthly_limit_gb must be positive")
    data = _load_bandwidth()
    existing = data.get("domains", {}).get(domain, {})
    data.setdefault("domains", {})[domain] = {
        "monthly_limit_gb": body.monthly_limit_gb,
        "alert_threshold_percent": body.alert_threshold_percent,
        "enabled": body.enabled,
        "block_on_exceed": body.block_on_exceed,
        "current_usage_bytes": existing.get("current_usage_bytes", 0),
        "reset_day": body.reset_day,
        "updated_at": datetime.datetime.now().isoformat(),
    }
    _save_bandwidth(data)
    if utils.is_linux():
        zone_name = domain.replace(".", "_")
        limit_mbps = int(body.monthly_limit_gb * 1024 * 8 / (30 * 86400))
        snippet = _generate_nginx_limit(zone_name, max(1, limit_mbps))
        snippet_path = Path(f"/etc/nginx/snippets/bandwidth-{domain}.conf")
        snippet_path.parent.mkdir(parents=True, exist_ok=True)
        if body.enabled:
            snippet_path.write_text(snippet)
        elif snippet_path.exists():
            snippet_path.unlink()
        utils.run_command(["nginx", "-t"], check=False)
        utils.service_action("reload", "nginx")
    return {"status": "updated", "domain": domain, "monthly_limit_gb": body.monthly_limit_gb}


@router.post("/reset")
def reset_usage(domain: str, user: dict = Depends(get_current_user)):
    data = _load_bandwidth()
    if domain not in data.get("domains", {}):
        raise HTTPException(status_code=404, detail="Domain not configured")
    data["domains"][domain]["current_usage_bytes"] = 0
    data["domains"][domain]["reset_at"] = datetime.datetime.now().isoformat()
    _save_bandwidth(data)
    return {"status": "reset", "domain": domain}


from pathlib import Path
