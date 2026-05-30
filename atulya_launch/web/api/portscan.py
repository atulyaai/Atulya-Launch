"""Port Scan Protection API — connection rate limiting."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/security/portscan", tags=["port-scan-protection"])

PORTSCAN_CONFIG_FILE = utils.CONFIG_DIR / "portscan.json"


def _load_portscan_config() -> dict:
    if PORTSCAN_CONFIG_FILE.exists():
        with open(PORTSCAN_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_portscan_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PORTSCAN_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_existing_connlimit_rules() -> list:
    result = utils.run_command(
        ["iptables", "-L", "INPUT", "-n", "--line-numbers"],
        check=False,
    )
    rules = []
    if not result or result.returncode != 0:
        return rules

    for line in result.stdout.splitlines():
        if "connlimit" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if "connlimit" in p:
                    rules.append({
                        "raw": line.strip(),
                        "rule_index": parts[0],
                    })
                    break
    return rules


def _apply_connlimit(connlimit: int, mask: int = 32, ports: Optional[list[int]] = None) -> dict:
    utils.run_command(["iptables", "-F", "PORTSCAN"], check=False)
    utils.run_command(["iptables", "-X", "PORTSCAN"], check=False)

    utils.run_command(["iptables", "-N", "PORTSCAN"], check=False)

    target_ports = ports or [80, 443, 22]
    for port in target_ports:
        utils.run_command([
            "iptables", "-A", "PORTSCAN",
            "-p", "tcp", "--dport", str(port),
            "-m", "connlimit", "--connlimit-above", str(connlimit),
            "--connlimit-mask", str(mask),
            "-j", "DROP",
        ], check=False)

    utils.run_command(["iptables", "-A", "PORTSCAN", "-j", "RETURN"], check=False)

    input_check = utils.run_command(
        ["iptables", "-C", "INPUT", "-j", "PORTSCAN"],
        check=False,
    )
    if not input_check or input_check.returncode != 0:
        utils.run_command(["iptables", "-I", "INPUT", "-j", "PORTSCAN"], check=False)

    return {"status": "applied", "connlimit": connlimit, "mask": mask, "ports": target_ports}


def _remove_connlimit() -> dict:
    utils.run_command(["iptables", "-D", "INPUT", "-j", "PORTSCAN"], check=False)
    utils.run_command(["iptables", "-F", "PORTSCAN"], check=False)
    utils.run_command(["iptables", "-X", "PORTSCAN"], check=False)
    return {"status": "removed"}


class PortscanEnable(BaseModel):
    connlimit: int = 10
    mask: int = 32
    ports: Optional[list[int]] = None


@router.get("")
def get_portscan_status(user: dict = Depends(get_current_user)):
    config = _load_portscan_config()
    rules = _get_existing_connlimit_rules()
    return {
        "enabled": config.get("enabled", False),
        "connlimit": config.get("connlimit", 10),
        "mask": config.get("mask", 32),
        "ports": config.get("ports", [80, 443, 22]),
        "active_rules": rules,
        "config": config,
    }


@router.post("/enable")
def enable_portscan_protection(body: PortscanEnable, user: dict = Depends(get_current_user)):
    if body.connlimit < 1 or body.connlimit > 10000:
        raise HTTPException(status_code=400, detail="connlimit must be between 1 and 10000")

    if body.mask < 0 or body.mask > 32:
        raise HTTPException(status_code=400, detail="mask must be between 0 and 32")

    result = _apply_connlimit(body.connlimit, body.mask, body.ports)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    config = {
        "enabled": True,
        "connlimit": body.connlimit,
        "mask": body.mask,
        "ports": body.ports or [80, 443, 22],
        "updated_at": datetime.now().isoformat(),
    }
    _save_portscan_config(config)

    return {"status": "enabled", "protection": config}


@router.post("/disable")
def disable_portscan_protection(user: dict = Depends(get_current_user)):
    result = _remove_connlimit()

    config = _load_portscan_config()
    config["enabled"] = False
    config["updated_at"] = datetime.now().isoformat()
    _save_portscan_config(config)

    return {"status": "disabled"}


@router.get("/connections")
def get_current_connections(user: dict = Depends(get_current_user)):
    result = utils.run_command(
        ["ss", "-tn", "state", "established"],
        check=False,
    )
    connections = []
    if result and result.stdout:
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                connections.append({
                    "proto": parts[0],
                    "recv": parts[1],
                    "send": parts[2],
                    "local": parts[3],
                    "peer": parts[4],
                })

    from collections import Counter
    ip_counts = Counter()
    for conn in connections:
        peer_addr = conn.get("peer", "")
        if ":" in peer_addr:
            ip = peer_addr.rsplit(":", 1)[0]
            ip_counts[ip] += 1

    return {
        "total_connections": len(connections),
        "connections_by_ip": dict(ip_counts.most_common(50)),
    }


@router.post("/purge")
def purge_connlimit(user: dict = Depends(get_current_user)):
    result = _remove_connlimit()
    config = _load_portscan_config()
    config["enabled"] = False
    _save_portscan_config(config)
    return result
