"""IP allowlist/blocklist management API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ipaccess", tags=["ipaccess"])

IP_ACCESS_FILE = utils.CONFIG_DIR / "ip_access.json"


def _load_ip_access() -> dict:
    if IP_ACCESS_FILE.exists():
        with open(IP_ACCESS_FILE, "r") as f:
            return json.load(f) or {"rules": []}
    return {"rules": []}


def _save_ip_access(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(IP_ACCESS_FILE, "w") as f:
        json.dump(data, f, indent=2)


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

    port_map = {
        "panel": "8000",
        "ssh": "22",
        "ftp": "21",
    }
    port = port_map.get(scope, "8000")

    if action == "allow":
        cmd = ["iptables", "-I", "INPUT", "-p", "tcp", "--dport", port, "-s", ip, "-j", "ACCEPT"]
    else:
        cmd = ["iptables", "-I", "INPUT", "-p", "tcp", "--dport", port, "-s", ip, "-j", "DROP"]

    utils.run_command(cmd, check=False)


def _remove_iptables_rule(ip: str, action: str, scope: str):
    if not utils.is_linux():
        return

    port_map = {
        "panel": "8000",
        "ssh": "22",
        "ftp": "21",
    }
    port = port_map.get(scope, "8000")

    if action == "allow":
        target = "ACCEPT"
    else:
        target = "DROP"

    cmd = ["iptables", "-D", "INPUT", "-p", "tcp", "--dport", port, "-s", ip, "-j", target]
    utils.run_command(cmd, check=False)


@router.get("/list")
def list_ip_access(user: dict = Depends(get_current_user)):
    data = _load_ip_access()
    return {"rules": data.get("rules", [])}


@router.post("")
def add_ip_rule(body: IPAccessRule, user: dict = Depends(get_current_user)):
    if not _validate_ip_or_cidr(body.ip_address):
        raise HTTPException(status_code=400, detail="Invalid IP address or CIDR notation")

    if body.action not in ("allow", "block"):
        raise HTTPException(status_code=400, detail="Action must be 'allow' or 'block'")
    if body.scope not in ("panel", "ssh", "ftp"):
        raise HTTPException(status_code=400, detail="Scope must be 'panel', 'ssh', or 'ftp'")

    data = _load_ip_access()
    rules = data.get("rules", [])

    for rule in rules:
        if rule["ip_address"] == body.ip_address and rule["scope"] == body.scope:
            raise HTTPException(status_code=409, detail="Rule already exists for this IP and scope")

    import datetime
    new_rule = {
        "id": len(rules) + 1,
        "ip_address": body.ip_address,
        "action": body.action,
        "scope": body.scope,
        "description": body.description or "",
        "created_at": datetime.datetime.now().isoformat(),
        "created_by": user.get("sub", "admin"),
    }
    rules.append(new_rule)
    data["rules"] = rules
    _save_ip_access(data)

    try:
        _apply_iptables_rule(body.ip_address, body.action, body.scope)
    except Exception as e:
        return {"status": "saved_but_not_applied", "rule": new_rule, "error": str(e)}

    return {"status": "added", "rule": new_rule}


@router.delete("/{rule_id}")
def remove_ip_rule(rule_id: int, user: dict = Depends(get_current_user)):
    data = _load_ip_access()
    rules = data.get("rules", [])

    target = None
    for rule in rules:
        if rule["id"] == rule_id:
            target = rule
            break

    if not target:
        raise HTTPException(status_code=404, detail="Rule not found")

    rules = [r for r in rules if r["id"] != rule_id]
    data["rules"] = rules
    _save_ip_access(data)

    try:
        _remove_iptables_rule(target["ip_address"], target["action"], target["scope"])
    except Exception:
        pass

    return {"status": "removed", "rule": target}


@router.post("/purge")
def purge_ip_rules(user: dict = Depends(get_current_user)):
    data = _load_ip_access()
    rules = data.get("rules", [])

    for rule in rules:
        try:
            _remove_iptables_rule(rule["ip_address"], rule["action"], rule["scope"])
        except Exception:
            pass

    data["rules"] = []
    _save_ip_access(data)

    return {"status": "purged", "removed": len(rules)}
