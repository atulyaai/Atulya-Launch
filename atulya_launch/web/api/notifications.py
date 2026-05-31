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
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


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
    with connect() as conn:
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE read = 0 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) as c FROM notifications").fetchone()["c"]
            unread = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE read = 0").fetchone()["c"]
        else:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) as c FROM notifications").fetchone()["c"]
            unread = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE read = 0").fetchone()["c"]
    notifications = [dict(r) for r in rows]
    for n in notifications:
        n["read"] = bool(n["read"])
    return {
        "notifications": notifications,
        "total": total,
        "unread": unread,
    }


@router.post("")
async def create_notification(body: NotificationCreate, user: dict = Depends(get_current_user)):
    if body.level not in ("info", "warning", "error", "success"):
        raise HTTPException(status_code=400, detail="Level must be info, warning, error, or success")

    notif_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    notification = {
        "id": notif_id,
        "title": body.title,
        "message": body.message,
        "level": body.level,
        "category": body.category,
        "read": False,
        "created_at": created_at,
    }

    with connect() as conn:
        conn.execute(
            "INSERT INTO notifications (id, title, message, level, category, read, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (notif_id, body.title, body.message, body.level, body.category, created_at),
        )

    await manager.broadcast(notification)

    return {"notification": notification}


@router.post("/read/{notif_id}")
def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM notifications WHERE id = ?", (notif_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")
        conn.execute(
            "UPDATE notifications SET read = 1, read_at = ? WHERE id = ?",
            (datetime.now().isoformat(), notif_id),
        )
    return {"status": "read", "id": notif_id}


@router.post("/read-all")
def mark_all_read(user: dict = Depends(get_current_user)):
    now = datetime.now().isoformat()
    with connect() as conn:
        conn.execute("UPDATE notifications SET read = 1, read_at = ? WHERE read = 0", (now,))
        count = conn.execute("SELECT COUNT(*) as c FROM notifications").fetchone()["c"]
    return {"status": "all_read", "count": count}


@router.delete("/{notif_id}")
def delete_notification(notif_id: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM notifications WHERE id = ?", (notif_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")
        conn.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
    return {"status": "deleted", "id": notif_id}


@router.delete("")
def clear_all_notifications(user: dict = Depends(get_current_user)):
    with connect() as conn:
        conn.execute("DELETE FROM notifications")
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
