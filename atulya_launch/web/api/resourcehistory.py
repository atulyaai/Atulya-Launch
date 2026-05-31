"""Resource history - CPU/RAM/disk time-series data collection API."""

import json
import time
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/monitor/history", tags=["resource-history"])

HISTORY_FILE = utils.CONFIG_DIR / "resource_history.json"
MAX_HISTORY_ENTRIES = 8640
COLLECTION_INTERVAL_SECONDS = 10


def _load_history() -> list:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r") as f:
            return json.load(f) or []
    return []


def _save_history(data: list):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f)


def _collect_sample() -> dict:
    timestamp = time.time()
    sample = {"timestamp": timestamp}

    try:
        import psutil
        sample["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        sample["cpu_count"] = psutil.cpu_count()

        mem = psutil.virtual_memory()
        sample["memory_total"] = mem.total
        sample["memory_used"] = mem.used
        sample["memory_percent"] = mem.percent

        disk = psutil.disk_usage("/")
        sample["disk_total"] = disk.total
        sample["disk_used"] = disk.used
        sample["disk_percent"] = disk.percent

        net = psutil.net_io_counters()
        sample["net_bytes_sent"] = net.bytes_sent
        sample["net_bytes_recv"] = net.bytes_recv
        sample["net_packets_sent"] = net.packets_sent
        sample["net_packets_recv"] = net.packets_recv

        load = [0, 0, 0]
        try:
            load = list(__import__("os").getloadavg())
        except (AttributeError, OSError):
            pass
        sample["load_1m"] = load[0]
        sample["load_5m"] = load[1]
        sample["load_15m"] = load[2]

    except ImportError:
        result = utils.run_command(["cat", "/proc/loadavg"], check=False)
        if result and result.returncode == 0:
            parts = result.stdout.strip().split()
            sample["load_1m"] = float(parts[0]) if len(parts) > 0 else 0
            sample["load_5m"] = float(parts[1]) if len(parts) > 1 else 0
            sample["load_15m"] = float(parts[2]) if len(parts) > 2 else 0

        result = utils.run_command(["free", "-b"], check=False)
        if result and result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        sample["memory_total"] = int(parts[1])
                        sample["memory_used"] = int(parts[2])
                        sample["memory_percent"] = round(int(parts[2]) / int(parts[1]) * 100, 1) if int(parts[1]) > 0 else 0

        result = utils.run_command(["df", "-B1", "/"], check=False)
        if result and result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 5:
                    sample["disk_total"] = int(parts[1])
                    sample["disk_used"] = int(parts[2])
                    sample["disk_percent"] = float(parts[4].rstrip("%"))

    return sample


@router.get("")
def get_resource_history(
    hours: int = Query(24, description="Hours of history to retrieve"),
    interval: Optional[int] = Query(None, description="Sampling interval in seconds"),
    user: dict = Depends(get_current_user)
):
    history = _load_history()
    cutoff = time.time() - (hours * 3600)
    filtered = [h for h in history if h.get("timestamp", 0) > cutoff]

    if interval and len(filtered) > 1:
        sampled = []
        last_ts = 0
        for h in filtered:
            if h["timestamp"] - last_ts >= interval:
                sampled.append(h)
                last_ts = h["timestamp"]
        filtered = sampled

    return {
        "hours": hours,
        "count": len(filtered),
        "samples": filtered,
    }


@router.post("/collect")
def trigger_collection(user: dict = Depends(get_current_user)):
    sample = _collect_sample()

    history = _load_history()
    history.append(sample)

    max_entries = MAX_HISTORY_ENTRIES
    if len(history) > max_entries:
        history = history[-max_entries:]

    _save_history(history)

    return {
        "status": "collected",
        "sample": sample,
        "total_samples": len(history),
    }


@router.get("/latest")
def get_latest_sample(user: dict = Depends(get_current_user)):
    history = _load_history()
    if not history:
        sample = _collect_sample()
        return {"sample": sample, "note": "freshly_collected"}
    return {"sample": history[-1]}


@router.delete("/purge")
def purge_history(user: dict = Depends(get_current_user)):
    _save_history([])
    return {"status": "purged"}
