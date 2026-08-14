"""Login history API."""

import datetime
from fastapi import APIRouter, Depends, Query

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/loginhistory", tags=["loginhistory"])


def log_login(username: str, success: bool, ip: str = "", user_agent: str = ""):
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO login_history (username, success, ip, user_agent, timestamp) VALUES (?, ?, ?, ?, ?)",
                (username, 1 if success else 0, ip, user_agent, datetime.datetime.now().isoformat()),
            )
    except Exception:
        pass


@router.get("")
def list_login_history(limit: int = Query(50, ge=1, le=500), user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, username, success, ip, user_agent, timestamp FROM login_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    history = []
    for r in rows:
        history.append({
            "id": r["id"],
            "username": r["username"],
            "success": bool(r["success"]),
            "ip": r["ip"],
            "user_agent": r["user_agent"],
            "timestamp": r["timestamp"],
        })
    return {"history": history}
