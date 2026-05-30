"""Network Stats API — bandwidth, connections, interface monitoring."""

import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/monitor/network", tags=["network-stats"])


def _parse_proc_net_dev() -> list:
    path = Path("/proc/net/dev")
    if not path.exists():
        return []
    lines = path.read_text().splitlines()[2:]
    interfaces = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 17:
            continue
        iface_name = parts[0].rstrip(":")
        interfaces.append({
            "interface": iface_name,
            "rx_bytes": int(parts[1]),
            "rx_packets": int(parts[2]),
            "rx_errors": int(parts[3]),
            "rx_dropped": int(parts[4]),
            "tx_bytes": int(parts[9]),
            "tx_packets": int(parts[10]),
            "tx_errors": int(parts[11]),
            "tx_dropped": int(parts[12]),
        })
    return interfaces


def _parse_netstat_connections() -> dict:
    result = utils.run_command(
        ["ss", "-tun", "state", "established"],
        check=False,
    )
    if not result or result.returncode != 0:
        result = utils.run_command(["netstat", "-tun"], check=False)

    total = 0
    by_state = {}
    by_protocol = {"tcp": 0, "tcp6": 0, "udp": 0, "udp6": 0}

    if result and result.stdout:
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 1:
                continue
            proto = parts[0].lower()
            total += 1
            state = parts[-1] if len(parts) > 1 else "UNKNOWN"
            by_state[state] = by_state.get(state, 0) + 1
            if proto in by_protocol:
                by_protocol[proto] += 1

    return {
        "total": total,
        "by_state": by_state,
        "by_protocol": by_protocol,
    }


def _get_bandwidth_per_interface(interval: float = 1.0) -> list:
    before = _parse_proc_net_dev()
    time.sleep(interval)
    after = _parse_proc_net_dev()

    before_map = {i["interface"]: i for i in before}
    results = []
    for iface in after:
        name = iface["interface"]
        if name == "lo":
            continue
        prev = before_map.get(name, {})
        rx_rate = (iface["rx_bytes"] - prev.get("rx_bytes", 0)) / interval
        tx_rate = (iface["tx_bytes"] - prev.get("tx_bytes", 0)) / interval
        results.append({
            "interface": name,
            "rx_bytes_per_sec": round(rx_rate),
            "tx_bytes_per_sec": round(tx_rate),
            "rx_total": iface["rx_bytes"],
            "tx_total": iface["tx_bytes"],
        })
    return results


def _get_interface_speed(interface: str) -> Optional[int]:
    speed_path = Path(f"/sys/class/net/{interface}/speed")
    if speed_path.exists():
        try:
            return int(speed_path.read_text().strip())
        except (ValueError, PermissionError):
            pass
    return None


def _get_operstate(interface: str) -> str:
    state_path = Path(f"/sys/class/net/{interface}/operstate")
    if state_path.exists():
        try:
            return state_path.read_text().strip()
        except PermissionError:
            pass
    return "unknown"


@router.get("")
def network_stats(user: dict = Depends(get_current_user)):
    interfaces = _parse_proc_net_dev()
    connections = _parse_netstat_connections()

    enriched = []
    for iface in interfaces:
        if iface["interface"] == "lo":
            continue
        iface["speed_mbps"] = _get_interface_speed(iface["interface"])
        iface["operstate"] = _get_operstate(iface["interface"])
        enriched.append(iface)

    return {
        "interfaces": enriched,
        "connections": connections,
        "summary": {
            "total_rx_bytes": sum(i["rx_bytes"] for i in interfaces if i["interface"] != "lo"),
            "total_tx_bytes": sum(i["tx_bytes"] for i in interfaces if i["interface"] != "lo"),
            "total_rx_packets": sum(i["rx_packets"] for i in interfaces if i["interface"] != "lo"),
            "total_tx_packets": sum(i["tx_packets"] for i in interfaces if i["interface"] != "lo"),
            "active_connections": connections["total"],
        },
    }


@router.get("/bandwidth")
def bandwidth_usage(
    interval: float = Query(1.0, ge=0.5, le=10.0),
    user: dict = Depends(get_current_user),
):
    bandwidth = _get_bandwidth_per_interface(interval=interval)
    return {"interval_seconds": interval, "interfaces": bandwidth}


@router.get("/connections")
def connection_stats(user: dict = Depends(get_current_user)):
    return _parse_netstat_connections()


@router.get("/interfaces")
def list_interfaces(user: dict = Depends(get_current_user)):
    interfaces = _parse_proc_net_dev()
    enriched = []
    for iface in interfaces:
        if iface["interface"] == "lo":
            continue
        iface["speed_mbps"] = _get_interface_speed(iface["interface"])
        iface["operstate"] = _get_operstate(iface["interface"])
        enriched.append(iface)
    return {"interfaces": enriched}
