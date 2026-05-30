"""IPv6 Management API."""

import json
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ipv6", tags=["ipv6"])

IPV6_CONFIG_FILE = utils.CONFIG_DIR / "ipv6.json"

SYSCTL_CONF = "/etc/sysctl.d/99-ipv6.conf"


def _load_ipv6_config() -> dict:
    if IPV6_CONFIG_FILE.exists():
        with open(IPV6_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_ipv6_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(IPV6_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _check_ipv6_enabled() -> bool:
    result = utils.run_command(["sysctl", "-n", "net.ipv6.conf.all.disable_ipv6"], check=False)
    if result and result.returncode == 0:
        return result.stdout.strip() == "0"
    return False


def _get_ipv6_addresses() -> list:
    result = utils.run_command(["ip", "-6", "addr", "show"], check=False)
    if not result or result.returncode != 0:
        return []

    addresses = []
    current_iface = ""
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and not line.startswith(" "):
            parts = line.split()
            if len(parts) >= 2:
                current_iface = parts[1].rstrip(":")
        if "inet6" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "inet6" and i + 1 < len(parts):
                    addr = parts[i + 1].split("/")[0]
                    prefix = parts[i + 1].split("/")[1] if "/" in parts[i + 1] else ""
                    scope = ""
                    for pp in parts[i + 2:]:
                        if pp.startswith("scope"):
                            scope = pp.split()[-1] if " " in pp else parts[parts.index(pp) + 1] if parts.index(pp) + 1 < len(parts) else ""
                            break
                    addresses.append({
                        "interface": current_iface,
                        "address": addr,
                        "prefix": prefix,
                        "scope": scope,
                    })
    return addresses


def _get_ipv6_default_gateway() -> Optional[str]:
    result = utils.run_command(["ip", "-6", "route", "show", "default"], check=False)
    if result and result.returncode == 0 and result.stdout.strip():
        parts = result.stdout.strip().split()
        if len(parts) >= 3:
            return parts[2]
    return None


def _apply_sysctl(enable: bool) -> dict:
    value = "0" if enable else "1"
    config_lines = [
        f"net.ipv6.conf.all.disable_ipv6 = {value}",
        f"net.ipv6.conf.default.disable_ipv6 = {value}",
    ]
    if not enable:
        config_lines.extend([
            "net.ipv6.conf.all.accept_ra = 0",
            "net.ipv6.conf.default.accept_ra = 0",
        ])

    try:
        Path(SYSCTL_CONF.parent).mkdir(parents=True, exist_ok=True)
        with open(SYSCTL_CONF, "w") as f:
            f.write("\n".join(config_lines) + "\n")
    except PermissionError:
        return {"error": "Permission denied writing sysctl config"}

    result = utils.run_command(["sysctl", "--system"], check=False)
    if result and result.returncode != 0:
        return {"warning": "sysctl applied with warnings"}

    return {"status": "applied"}


class IPv6Enable(BaseModel):
    enable: bool = True


class IPv6AddressAdd(BaseModel):
    interface: str
    address: str
    prefix: int = 64


@router.get("/status")
def ipv6_status(user: dict = Depends(get_current_user)):
    enabled = _check_ipv6_enabled()
    addresses = _get_ipv6_addresses()
    gateway = _get_ipv6_default_gateway()
    config = _load_ipv6_config()

    return {
        "enabled": enabled,
        "gateway": gateway,
        "addresses": addresses,
        "total_addresses": len(addresses),
        "configured": config.get("configured", False),
    }


@router.post("/enable")
def enable_ipv6(user: dict = Depends(get_current_user)):
    result = _apply_sysctl(enable=True)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    config = _load_ipv6_config()
    config["enabled"] = True
    config["configured"] = True
    _save_ipv6_config(config)

    return {"status": "enabled", "result": result}


@router.post("/disable")
def disable_ipv6(user: dict = Depends(get_current_user)):
    result = _apply_sysctl(enable=False)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    config = _load_ipv6_config()
    config["enabled"] = False
    config["configured"] = True
    _save_ipv6_config(config)

    return {"status": "disabled", "result": result}


@router.get("/addresses")
def list_ipv6_addresses(user: dict = Depends(get_current_user)):
    addresses = _get_ipv6_addresses()
    gateway = _get_ipv6_default_gateway()
    return {"addresses": addresses, "gateway": gateway}


@router.post("/addresses")
def add_ipv6_address(body: IPv6AddressAdd, user: dict = Depends(get_current_user)):
    if body.prefix < 1 or body.prefix > 128:
        raise HTTPException(status_code=400, detail="Prefix must be between 1 and 128")

    addr_str = f"{body.address}/{body.prefix}"
    result = utils.run_command(
        ["ip", "-6", "addr", "add", addr_str, "dev", body.interface],
        check=False,
    )
    if result and result.returncode != 0:
        error_msg = result.stderr.strip() if hasattr(result, "stderr") and result.stderr else "Failed to add address"
        raise HTTPException(status_code=500, detail=error_msg)

    return {"status": "added", "address": body.address, "interface": body.interface, "prefix": body.prefix}


@router.delete("/addresses/{interface}/{address}")
def remove_ipv6_address(interface: str, address: str, user: dict = Depends(get_current_user)):
    result = utils.run_command(
        ["ip", "-6", "addr", "del", address, "dev", interface],
        check=False,
    )
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to remove address")

    return {"status": "removed", "address": address, "interface": interface}
