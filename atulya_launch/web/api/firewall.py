"""Firewall management API (iptables / nftables)."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/firewall", tags=["firewall"])


class RuleCreate(BaseModel):
    chain: str = "INPUT"
    protocol: str = "tcp"
    port: int
    action: str = "ACCEPT"
    source: Optional[str] = None
    comment: Optional[str] = None


class RuleUpdate(BaseModel):
    chain: Optional[str] = None
    protocol: Optional[str] = None
    port: Optional[int] = None
    action: Optional[str] = None
    source: Optional[str] = None
    comment: Optional[str] = None


def _parse_iptables_rules() -> list:
    result = utils.run_command(["iptables", "-L", "-n", "--line-numbers"], check=False)
    if not result or result.returncode != 0:
        return []
    rules = []
    current_chain = "INPUT"
    idx = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Chain"):
            current_chain = line.split()[1]
            continue
        if line.startswith("num") or not line or line.startswith("target"):
            continue
        parts = line.split(None, 5)
        if len(parts) < 5:
            continue
        idx += 1
        rule = {
            "id": idx,
            "chain": current_chain,
            "target": parts[0],
            "prot": parts[1],
            "opt": parts[2],
            "source": parts[3],
            "destination": parts[4],
            "extra": parts[5] if len(parts) > 5 else "",
        }
        rules.append(rule)
    return rules


@router.get("/rules")
def list_rules(user: dict = Depends(get_current_user)):
    return {"rules": _parse_iptables_rules()}


@router.post("/rules")
def add_rule(body: RuleCreate, user: dict = Depends(get_current_user)):
    args = ["iptables", "-A", body.chain, "-p", body.protocol, "--dport", str(body.port), "-j", body.action]
    if body.source:
        args.extend(["-s", body.source])
    if body.comment:
        args.extend(["-m", "comment", "--comment", body.comment])
    result = utils.run_command(args, check=False)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to add rule")
    return {"status": "rule added", "chain": body.chain, "port": body.port}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, user: dict = Depends(get_current_user)):
    rules = _parse_iptables_rules()
    target = None
    for r in rules:
        if r["id"] == rule_id:
            target = r
            break
    if not target:
        raise HTTPException(status_code=404, detail="Rule not found")
    args = ["iptables", "-D", target["chain"]]
    parts = []
    if target.get("prot") and target["prot"] != "all":
        parts.extend(["-p", target["prot"]])
    if target.get("extra"):
        extra = target["extra"]
        if "dpt:" in extra:
            port = extra.split("dpt:")[-1]
            parts.extend(["--dport", port])
        if "spt:" in extra:
            port = extra.split("spt:")[-1]
            parts.extend(["--sport", port])
    args.extend(parts)
    args.extend(["-j", target["target"]])
    utils.run_command(args, check=False)
    return {"status": "deleted", "id": rule_id}


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, user: dict = Depends(get_current_user)):
    delete_rule(rule_id, user)
    create_body = RuleCreate(
        chain=body.chain or "INPUT",
        protocol=body.protocol or "tcp",
        port=body.port or 80,
        action=body.action or "ACCEPT",
        source=body.source,
        comment=body.comment,
    )
    return add_rule(create_body, user)


@router.get("/status")
def firewall_status(user: dict = Depends(get_current_user)):
    result = utils.run_command(["iptables", "-L", "-n"], check=False)
    active = result is not None and result.returncode == 0
    return {"active": active, "backend": "iptables"}


@router.post("/enable")
def enable_firewall(user: dict = Depends(get_current_user)):
    utils.run_command(["iptables", "-P", "INPUT", "ACCEPT"], check=False)
    utils.run_command(["iptables", "-P", "FORWARD", "ACCEPT"], check=False)
    utils.run_command(["iptables", "-P", "OUTPUT", "ACCEPT"], check=False)
    return {"status": "enabled"}


@router.post("/disable")
def disable_firewall(user: dict = Depends(get_current_user)):
    utils.run_command(["iptables", "-F"], check=False)
    utils.run_command(["iptables", "-X"], check=False)
    utils.run_command(["iptables", "-P", "INPUT", "ACCEPT"], check=False)
    utils.run_command(["iptables", "-P", "FORWARD", "ACCEPT"], check=False)
    utils.run_command(["iptables", "-P", "OUTPUT", "ACCEPT"], check=False)
    return {"status": "disabled"}
