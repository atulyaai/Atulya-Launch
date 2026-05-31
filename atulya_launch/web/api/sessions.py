"""Session management API."""

import datetime
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def create_session(user: str, ip: str = "", user_agent: str = "") -> str:
    token = secrets.token_hex(32)
    now = datetime.datetime.now().isoformat()
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO panel_sessions (token, username, ip, user_agent, created_at, last_active) VALUES (?, ?, ?, ?, ?, ?)",
                (token, user, ip, user_agent, now, now),
            )
    except Exception:
        pass
    return token


def get_session(token: str) -> Optional[dict]:
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT token, username, ip, user_agent, created_at, last_active FROM panel_sessions WHERE token = ?",
                (token,),
            ).fetchone()
        if row:
            return {
                "user": row["username"],
                "ip": row["ip"],
                "user_agent": row["user_agent"],
                "created_at": row["created_at"],
                "last_active": row["last_active"],
            }
    except Exception:
        pass
    return None


def touch_session(token: str):
    try:
        with connect() as conn:
            conn.execute(
                "UPDATE panel_sessions SET last_active = ? WHERE token = ?",
                (datetime.datetime.now().isoformat(), token),
            )
    except Exception:
        pass


@router.get("")
def list_sessions(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT token, username, ip, user_agent, created_at, last_active FROM panel_sessions",
        ).fetchall()
    result = []
    for r in rows:
        result.append({
            "token_preview": r["token"][:8] + "...",
            "user": r["username"],
            "ip": r["ip"],
            "created_at": r["created_at"],
            "last_active": r["last_active"],
        })
    return {"sessions": result}


@router.delete("/{token_preview}")
def revoke_session(token_preview: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT token FROM panel_sessions WHERE token LIKE ?",
            (token_preview + "%",),
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Session not found")
        conn.execute(
            "DELETE FROM panel_sessions WHERE token LIKE ?",
            (token_preview + "%",),
        )
    return {"status": "revoked"}
