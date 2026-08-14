"""System monitoring API with WebSocket and SSE live stream."""

import asyncio
import json
import time

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from atulya_launch import core
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


def _get_psutil_status() -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        return {
            "cpu_percent": cpu,
            "memory": {"total": mem.total, "used": mem.used, "percent": mem.percent},
            "disk": {"total": disk.total, "used": disk.used, "percent": disk.percent},
            "network": {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv},
            "uptime": psutil.boot_time(),
        }
    except ImportError:
        return {"error": "psutil not installed"}


def _get_psutil_processes(sort_by: str = "cpu", limit: int = 20) -> list:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu": info.get("cpu_percent", 0) or 0,
                "memory": round((info.get("memory_percent", 0) or 0), 1),
                "status": info.get("status", "unknown"),
            })
        key = "cpu" if sort_by == "cpu" else "memory"
        procs.sort(key=lambda x: x.get(key, 0), reverse=True)
        return procs[:limit]
    except ImportError:
        return []


@router.get("/status")
def system_status(user: dict = Depends(get_current_user)):
    return _get_psutil_status()


@router.get("/processes")
def top_processes(sort_by: str = Query("cpu"), limit: int = Query(20), user: dict = Depends(get_current_user)):
    return {"processes": _get_psutil_processes(sort_by=sort_by, limit=limit)}


@router.get("/logs/{log_type}")
def get_logs(log_type: str, lines: int = Query(50), user: dict = Depends(get_current_user)):
    source_map = {
        "syslog": "syslog",
        "auth": "auth",
        "nginx": "nginx",
        "error": "error",
        "access": "access",
    }
    source = source_map.get(log_type, log_type)
    return core.log_view(source=source, lines=lines)


# ── WebSocket live monitor ────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


@router.websocket("/ws/monitor")
async def monitor_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            status_data = _get_psutil_status()
            await websocket.send_json(status_data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ── SSE live monitor (Server-Sent Events) ────────────────────────────────

@router.get("/stream")
def monitor_sse(user: dict = Depends(get_current_user)):
    """SSE endpoint for real-time CPU/RAM/disk/network monitoring."""
    def event_generator():
        while True:
            data = _get_psutil_status()
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
