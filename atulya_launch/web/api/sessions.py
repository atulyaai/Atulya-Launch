"""Session management API."""

import datetime
import json
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _sessions_file():
    return utils.CONFIG_DIR / "sessions.json"


def _load_sessions() -> dict:
    p = _sessions_file()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save_sessions(data: dict):
    p = _sessions_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def create_session(user: str, ip: str = "", user_agent: str = "") -> str:
    token = secrets.token_hex(32)
    sessions = _load_sessions()
    sessions[token] = {
        "user": user,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": datetime.datetime.now().isoformat(),
        "last_active": datetime.datetime.now().isoformat(),
    }
    _save_sessions(sessions)
    return token


def get_session(token: str) -> Optional[dict]:
    sessions = _load_sessions()
    return sessions.get(token)


def touch_session(token: str):
    sessions = _load_sessions()
    if token in sessions:
        sessions[token]["last_active"] = datetime.datetime.now().isoformat()
        _save_sessions(sessions)


@router.get("")
def list_sessions(user: dict = Depends(get_current_user)):
    sessions = _load_sessions()
    result = []
    for token, data in sessions.items():
        result.append({
            "token_preview": token[:8] + "...",
            "user": data.get("user"),
            "ip": data.get("ip"),
            "created_at": data.get("created_at"),
            "last_active": data.get("last_active"),
        })
    return {"sessions": result}


@router.delete("/{token_preview}")
def revoke_session(token_preview: str, user: dict = Depends(get_current_user)):
    sessions = _load_sessions()
    to_delete = [t for t in sessions if t.startswith(token_preview)]
    if not to_delete:
        raise HTTPException(status_code=404, detail="Session not found")
    for t in to_delete:
        del sessions[t]
    _save_sessions(sessions)
    return {"status": "revoked"}
