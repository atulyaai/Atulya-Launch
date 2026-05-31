"""IP allowlist/blocklist management API."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/ipaccess", tags=["ipaccess"])


class IPAccessRule(BaseModel):
    ip_address: str
    action: str = "allow"
    scope: str = "panel"
    description: Optional[str] = None


def _validate_ip_or_cidr(ip: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_network(ip, strict=False)
        return True
    except ValueError:
        return False


def _apply_iptables_rule(ip: str, action: str, scope: str):
    if not utils.is_linux():
        return
    port_map = {"panel": "8000", "ssh": "22", "ftp": "21"}
    port = port_map.get(scope, "8000")
    if action == "allow":
        cmd = ["iptables", "-I", "INPUT", "-p", "tcp", "--dport", port, "-s", ip, "-j", "ACCEPT"]
    else:
        cmd = ["iptables", "-I", "INPUT", "-p", "tcp", "--dport", port, "-s", ip, "-j", "DROP"]
    utils.run_command(cmd, check=False)


def _remove_iptables_rule(ip: str, action: str, scope: str):
    if not utils.is_linux():
        return
    port_map = {"panel": "8000", "ssh": "22", "ftp": "21"}
    port = port_map.get(scope, "8000")
    target = "ACCEPT" if action == "allow" else "DROP"
    cmd = ["iptables", "-D", "INPUT", "-p", "tcp", "--dport", port, "-s", ip, "-j", target]
    utils.run_command(cmd, check=False)


@router.get("/list")
def list_ip_access(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, ip_address, action, scope, description, created_at, created_by FROM ip_access_rules ORDER BY id",
        ).fetchall()
    return {"rules": [dict(r) for r in rows]}


@router.post("")
def add_ip_rule(body: IPAccessRule, user: dict = Depends(get_current_user)):
    if not _validate_ip_or_cidr(body.ip_address):
        raise HTTPException(status_code=400, detail="Invalid IP address or CIDR notation")
    if body.action not in ("allow", "block"):
        raise HTTPException(status_code=400, detail="Action must be 'allow' or 'block'")
    if body.scope not in ("panel", "ssh", "ftp"):
        raise HTTPException(status_code=400, detail="Scope must be 'panel', 'ssh', or 'ftp'")
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM ip_access_rules WHERE ip_address = ? AND scope = ?",
            (body.ip_address, body.scope),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Rule already exists for this IP and scope")
        now = datetime.datetime.now().isoformat()
        cursor = conn.execute(
            "INSERT INTO ip_access_rules (ip_address, action, scope, description, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (body.ip_address, body.action, body.scope, body.description or "", now, user.get("sub", "admin")),
        )
        rule_id = cursor.lastrowid
        new_rule = {
            "id": rule_id,
            "ip_address": body.ip_address,
            "action": body.action,
            "scope": body.scope,
            "description": body.description or "",
            "created_at": now,
            "created_by": user.get("sub", "admin"),
        }
    try:
        _apply_iptables_rule(body.ip_address, body.action, body.scope)
    except Exception as e:
        return {"status": "saved_but_not_applied", "rule": new_rule, "error": str(e)}
    return {"status": "added", "rule": new_rule}


@router.delete("/{rule_id}")
def remove_ip_rule(rule_id: int, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT id, ip_address, action, scope FROM ip_access_rules WHERE id = ?", (rule_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")
        target = dict(row)
        conn.execute("DELETE FROM ip_access_rules WHERE id = ?", (rule_id,))
    try:
        _remove_iptables_rule(target["ip_address"], target["action"], target["scope"])
    except Exception:
        pass
    return {"status": "removed", "rule": target}


@router.post("/purge")
def purge_ip_rules(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT ip_address, action, scope FROM ip_access_rules").fetchall()
        for r in rows:
            try:
                _remove_iptables_rule(r["ip_address"], r["action"], r["scope"])
            except Exception:
                pass
        conn.execute("DELETE FROM ip_access_rules")
    return {"status": "purged", "removed": len(rows)}
