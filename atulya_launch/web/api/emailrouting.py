"""Email routing and catch-all management API."""

import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/email", tags=["email-routing"])


class RoutingConfig(BaseModel):
    mode: str = "local"
    relay_host: Optional[str] = None
    relay_port: int = 25
    relay_username: Optional[str] = None
    relay_password: Optional[str] = None


class CatchAllConfig(BaseModel):
    address: str
    enabled: bool = True


def _generate_postfix_relay(domain: str, config: RoutingConfig) -> str:
    lines = [
        f"relay_domains = {domain}",
        f"transport_maps = hash:/etc/postfix/transport",
    ]
    if config.relay_host:
        lines.append(f"relayhost = [{config.relay_host}]:{config.relay_port}")
    if config.relay_username:
        lines.append(f"smtp_sasl_auth_enable = yes")
        lines.append(f"smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd")
        lines.append(f"smtp_sasl_security_options = noanonymous")
    return "\n".join(lines)


@router.get("/routing/{domain}")
def get_routing(domain: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT mode, relay_host, relay_port, relay_username, updated_at FROM email_routing WHERE domain = ?",
            (domain,),
        ).fetchone()
    if row:
        routing = dict(row)
    else:
        routing = {"mode": "local"}
    return {"domain": domain, "routing": routing}


@router.put("/routing/{domain}")
def set_routing(domain: str, body: RoutingConfig, user: dict = Depends(get_current_user)):
    if body.mode not in ("local", "relay", "remote"):
        raise HTTPException(status_code=400, detail="Mode must be one of: local, relay, remote")
    if body.mode == "relay" and not body.relay_host:
        raise HTTPException(status_code=400, detail="relay_host is required for relay mode")
    now = datetime.datetime.now().isoformat()
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO email_routing (domain, mode, relay_host, relay_port, relay_username, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (domain, body.mode, body.relay_host, body.relay_port, body.relay_username, now),
        )
    if body.mode == "relay" and body.relay_host:
        relay_conf = _generate_postfix_relay(domain, body)
        conf_path = Path("/etc/postfix/conf.d")
        conf_path.mkdir(parents=True, exist_ok=True)
        (conf_path / f"relay_{domain}.conf").write_text(relay_conf)
        if body.relay_username and body.relay_password:
            sasl_path = Path("/etc/postfix/sasl_passwd")
            sasl_entry = f"[{body.relay_host}]:{body.relay_port} {body.relay_username}:{body.relay_password}"
            existing = sasl_path.read_text() if sasl_path.exists() else ""
            if body.relay_host not in existing:
                sasl_path.write_text(existing + sasl_entry + "\n")
            utils.run_command(["postmap", "/etc/postfix/sasl_passwd"], check=False)
    return {"status": "updated", "domain": domain, "mode": body.mode}


@router.get("/catchall/{domain}")
def get_catchall(domain: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT address, enabled, updated_at FROM email_catchall WHERE domain = ?",
            (domain,),
        ).fetchone()
    if row:
        catchall = {"address": row["address"], "enabled": bool(row["enabled"])}
    else:
        catchall = {"address": "", "enabled": False}
    return {"domain": domain, "catchall": catchall}


@router.put("/catchall/{domain}")
def set_catchall(domain: str, body: CatchAllConfig, user: dict = Depends(get_current_user)):
    now = datetime.datetime.now().isoformat()
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO email_catchall (domain, address, enabled, updated_at)
               VALUES (?, ?, ?, ?)""",
            (domain, body.address, 1 if body.enabled else 0, now),
        )
    if body.enabled and body.address:
        vmap_path = Path(f"/etc/postfix/virtual_{domain}")
        existing = vmap_path.read_text() if vmap_path.exists() else ""
        lines = [l for l in existing.splitlines() if not l.startswith(f"@{domain}")]
        lines.append(f"@{domain}  {body.address}")
        vmap_path.write_text("\n".join(lines) + "\n")
        utils.run_command(["postmap", str(vmap_path)], check=False)
        utils.service_action("reload", "postfix")
    return {"status": "updated", "domain": domain, "catchall": body.address}
