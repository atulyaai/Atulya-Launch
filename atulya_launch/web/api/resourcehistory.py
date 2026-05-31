"""Resource history - CPU/RAM/disk time-series data collection API."""

import json
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/monitor/history", tags=["resource-history"])

MAX_HISTORY_ENTRIES = 8640
COLLECTION_INTERVAL_SECONDS = 10


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
    cutoff = time.time() - (hours * 3600)
    with connect() as conn:
        rows = conn.execute(
            "SELECT sample_json, timestamp FROM resource_history WHERE timestamp > ? ORDER BY timestamp",
            (cutoff,),
        ).fetchall()
    filtered = [json.loads(r["sample_json"]) for r in rows]

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
    ts = sample.get("timestamp", time.time())

    with connect() as conn:
        conn.execute(
            "INSERT INTO resource_history (sample_json, timestamp) VALUES (?, ?)",
            (json.dumps(sample), ts),
        )
        count = conn.execute("SELECT COUNT(*) as c FROM resource_history").fetchone()["c"]
        if count > MAX_HISTORY_ENTRIES:
            conn.execute(
                "DELETE FROM resource_history WHERE id NOT IN (SELECT id FROM resource_history ORDER BY timestamp DESC LIMIT ?)",
                (MAX_HISTORY_ENTRIES,),
            )
        total = conn.execute("SELECT COUNT(*) as c FROM resource_history").fetchone()["c"]

    return {
        "status": "collected",
        "sample": sample,
        "total_samples": total,
    }


@router.get("/latest")
def get_latest_sample(user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT sample_json FROM resource_history ORDER BY timestamp DESC LIMIT 1",
        ).fetchone()
    if not row:
        sample = _collect_sample()
        return {"sample": sample, "note": "freshly_collected"}
    return {"sample": json.loads(row["sample_json"])}


@router.delete("/purge")
def purge_history(user: dict = Depends(get_current_user)):
    with connect() as conn:
        conn.execute("DELETE FROM resource_history")
    return {"status": "purged"}
