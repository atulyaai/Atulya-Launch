"""Bandwidth monitoring API per interface and per domain."""

import json
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/monitor/bandwidth", tags=["bandwidth"])


def _get_interface_stats() -> list:
    try:
        import psutil
        stats = []
        net_io = psutil.net_io_counters(pernic=True)
        addrs = psutil.net_if_addrs()
        for iface, counters in net_io.items():
            stat = {
                "interface": iface,
                "bytes_sent": counters.bytes_sent,
                "bytes_recv": counters.bytes_recv,
                "packets_sent": counters.packets_sent,
                "packets_recv": counters.packets_recv,
                "errin": counters.errin,
                "errout": counters.errout,
                "dropin": counters.dropin,
                "dropout": counters.dropout,
            }
            if iface in addrs:
                for addr in addrs[iface]:
                    if addr.family.name == "AF_INET":
                        stat["ipv4"] = addr.address
                    elif addr.family.name == "AF_INET6":
                        stat["ipv6"] = addr.address
            stats.append(stat)
        return stats
    except ImportError:
        return _get_interface_stats_fallback()


def _get_interface_stats_fallback() -> list:
    stats = []
    result = utils.run_command(["cat", "/proc/net/dev"], check=False)
    if result and result.returncode == 0:
        for line in result.stdout.splitlines()[2:]:
            line = line.strip()
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            parts = data.split()
            if len(parts) >= 10:
                stats.append({
                    "interface": iface.strip(),
                    "bytes_recv": int(parts[0]),
                    "packets_recv": int(parts[1]),
                    "errin": int(parts[2]),
                    "dropin": int(parts[3]),
                    "bytes_sent": int(parts[8]),
                    "packets_sent": int(parts[9]),
                    "errout": int(parts[10]),
                    "dropout": int(parts[11]),
                })
    return stats


def _get_domain_bandwidth() -> list:
    bandwidth_data = []

    nginx_log_paths = [
        "/var/log/nginx/access.log",
        "/var/log/nginx/access.log.1",
    ]

    domain_bytes = {}
    for log_path in nginx_log_paths:
        try:
            result = utils.run_command(["cat", log_path], check=False)
            if result and result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 10:
                        server_name = None
                        for i, p in enumerate(parts):
                            if p == "Host:" and i + 1 < len(parts):
                                server_name = parts[i + 1].split(":")[0]
                                break
                            if i > 0 and parts[i - 1] == "Host:":
                                server_name = p.split(":")[0]
                                break

                        if server_name:
                            response_size = int(parts[9]) if parts[9].isdigit() else 0
                            if server_name not in domain_bytes:
                                domain_bytes[server_name] = {"bytes": 0, "requests": 0}
                            domain_bytes[server_name]["bytes"] += response_size
                            domain_bytes[server_name]["requests"] += 1
        except Exception:
            continue

    config = utils.load_config()
    sites = config.get("sites", {})
    for domain in sites:
        if domain not in domain_bytes:
            domain_bytes[domain] = {"bytes": 0, "requests": 0}

    for domain, data in domain_bytes.items():
        bandwidth_data.append({
            "domain": domain,
            "bytes_transferred": data["bytes"],
            "requests": data["requests"],
            "avg_bytes_per_request": data["bytes"] // data["requests"] if data["requests"] > 0 else 0,
        })

    bandwidth_data.sort(key=lambda x: x["bytes_transferred"], reverse=True)
    return bandwidth_data


@router.get("")
def get_bandwidth_stats(user: dict = Depends(get_current_user)):
    return {"interfaces": _get_interface_stats()}


@router.get("/{domain}")
def get_domain_bandwidth(domain: str, user: dict = Depends(get_current_user)):
    all_domains = _get_domain_bandwidth()
    for d in all_domains:
        if d["domain"] == domain:
            return {"domain": d}

    config = utils.load_config()
    sites = config.get("sites", {})
    if domain not in sites:
        raise HTTPException(status_code=404, detail="Domain not found")

    return {
        "domain": {
            "domain": domain,
            "bytes_transferred": 0,
            "requests": 0,
            "avg_bytes_per_request": 0,
        }
    }


@router.get("/all/summary")
def get_bandwidth_summary(user: dict = Depends(get_current_user)):
    interfaces = _get_interface_stats()
    total_sent = sum(i["bytes_sent"] for i in interfaces)
    total_recv = sum(i["bytes_recv"] for i in interfaces)

    return {
        "total_bytes_sent": total_sent,
        "total_bytes_recv": total_recv,
        "total_sent_mb": round(total_sent / 1048576, 2),
        "total_recv_mb": round(total_recv / 1048576, 2),
        "interfaces_count": len(interfaces),
    }
