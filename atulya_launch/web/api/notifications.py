"""Notification System API with WebSocket push."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

NOTIFICATIONS_FILE = utils.CONFIG_DIR / "notifications.json"


def _load_notifications() -> list:
    if NOTIFICATIONS_FILE.exists():
        with open(NOTIFICATIONS_FILE, "r") as f:
            return json.load(f) or []
    return []


def _save_notifications(data: list):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(NOTIFICATIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _find_notification(notifications: list, notif_id: str) -> Optional[dict]:
    for n in notifications:
        if n.get("id") == notif_id:
            return n
    return None


class NotificationCreate(BaseModel):
    title: str
    message: str
    level: str = "info"
    category: str = "system"


class NotificationManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, notification: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(notification)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = NotificationManager()


@router.get("")
def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    user: dict = Depends(get_current_user),
):
    notifications = _load_notifications()
    if unread_only:
        notifications = [n for n in notifications if not n.get("read", False)]
    notifications.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {
        "notifications": notifications[:limit],
        "total": len(notifications),
        "unread": sum(1 for n in notifications if not n.get("read", False)),
    }


@router.post("")
async def create_notification(body: NotificationCreate, user: dict = Depends(get_current_user)):
    if body.level not in ("info", "warning", "error", "success"):
        raise HTTPException(status_code=400, detail="Level must be info, warning, error, or success")

    notification = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "message": body.message,
        "level": body.level,
        "category": body.category,
        "read": False,
        "created_at": datetime.now().isoformat(),
    }

    notifications = _load_notifications()
    notifications.append(notification)
    _save_notifications(notifications)

    await manager.broadcast(notification)

    return {"notification": notification}


@router.post("/read/{notif_id}")
def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    notifications = _load_notifications()
    notif = _find_notification(notifications, notif_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif["read"] = True
    notif["read_at"] = datetime.now().isoformat()
    _save_notifications(notifications)
    return {"status": "read", "id": notif_id}


@router.post("/read-all")
def mark_all_read(user: dict = Depends(get_current_user)):
    notifications = _load_notifications()
    for n in notifications:
        if not n.get("read", False):
            n["read"] = True
            n["read_at"] = datetime.now().isoformat()
    _save_notifications(notifications)
    return {"status": "all_read", "count": len(notifications)}


@router.delete("/{notif_id}")
def delete_notification(notif_id: str, user: dict = Depends(get_current_user)):
    notifications = _load_notifications()
    notif = _find_notification(notifications, notif_id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notifications = [n for n in notifications if n.get("id") != notif_id]
    _save_notifications(notifications)
    return {"status": "deleted", "id": notif_id}


@router.delete("")
def clear_all_notifications(user: dict = Depends(get_current_user)):
    _save_notifications([])
    return {"status": "cleared"}


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
