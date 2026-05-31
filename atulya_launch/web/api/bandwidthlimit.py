"""Bandwidth limiting API for sites."""

import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/sites/{domain}/bandwidth-limit", tags=["bandwidth"])


class BandwidthConfig(BaseModel):
    monthly_limit_gb: float = 100.0
    alert_threshold_percent: float = 80.0
    enabled: bool = True
    block_on_exceed: bool = False
    current_usage_bytes: int = 0
    reset_day: int = 1


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
    with connect() as conn:
        row = conn.execute(
            "SELECT monthly_limit_gb, alert_threshold_percent, enabled, block_on_exceed, current_usage_bytes, reset_day FROM bandwidth_config WHERE domain = ?",
            (domain,),
        ).fetchone()
    if row:
        config = dict(row)
    else:
        config = {
            "monthly_limit_gb": 100.0,
            "alert_threshold_percent": 80.0,
            "enabled": False,
            "block_on_exceed": False,
            "current_usage_bytes": 0,
            "reset_day": 1,
        }
    usage_pct = 0
    limit_bytes = config.get("monthly_limit_gb", 100) * (1024 ** 3)
    if limit_bytes > 0:
        usage_pct = round((config.get("current_usage_bytes", 0) / limit_bytes) * 100, 2)
    return {
        "domain": domain,
        "bandwidth": {
            **config,
            "usage_percent": usage_pct,
            "limit_human": _bytes_to_human(int(limit_bytes)),
            "usage_human": _bytes_to_human(config.get("current_usage_bytes", 0)),
            "remaining_human": _bytes_to_human(max(0, int(limit_bytes) - config.get("current_usage_bytes", 0))),
        },
    }


@router.put("")
def set_bandwidth(domain: str, body: BandwidthConfig, user: dict = Depends(get_current_user)):
    if body.monthly_limit_gb <= 0:
        raise HTTPException(status_code=400, detail="monthly_limit_gb must be positive")
    now = datetime.datetime.now().isoformat()
    with connect() as conn:
        existing = conn.execute(
            "SELECT current_usage_bytes FROM bandwidth_config WHERE domain = ?", (domain,),
        ).fetchone()
        current_usage = existing["current_usage_bytes"] if existing else 0
        conn.execute(
            """INSERT OR REPLACE INTO bandwidth_config
               (domain, monthly_limit_gb, alert_threshold_percent, enabled, block_on_exceed, current_usage_bytes, reset_day, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (domain, body.monthly_limit_gb, body.alert_threshold_percent,
             1 if body.enabled else 0, 1 if body.block_on_exceed else 0,
             current_usage, body.reset_day, now),
        )
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
    with connect() as conn:
        row = conn.execute("SELECT domain FROM bandwidth_config WHERE domain = ?", (domain,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Domain not configured")
        conn.execute(
            "UPDATE bandwidth_config SET current_usage_bytes = 0 WHERE domain = ?",
            (domain,),
        )
    return {"status": "reset", "domain": domain}
