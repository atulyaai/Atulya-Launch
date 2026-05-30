"""System monitoring API with WebSocket live stream."""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from atulya_launch import core
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/status")
def system_status(user: dict = Depends(get_current_user)):
    try:
        return core.monitor_status()
    except ImportError:
        return {"error": "psutil not installed"}


@router.get("/processes")
def top_processes(sort_by: str = Query("cpu"), limit: int = Query(20), user: dict = Depends(get_current_user)):
    try:
        return {"processes": core.monitor_processes(sort_by=sort_by, limit=limit)}
    except ImportError:
        return {"error": "psutil not installed"}


@router.get("/logs/{log_type}")
def get_logs(log_type: str, lines: int = Query(50), user: dict = Depends(get_current_user)):
    return core.monitor_logs(log_type=log_type, lines=lines)


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
            try:
                status_data = core.monitor_status()
            except Exception:
                status_data = {"error": "psutil not available"}
            await websocket.send_json(status_data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
