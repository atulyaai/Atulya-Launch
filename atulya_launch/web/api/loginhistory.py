"""Login history API."""

import datetime
import json
from typing import Optional
from fastapi import APIRouter, Depends, Query

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/loginhistory", tags=["loginhistory"])


def _loginhistory_file():
    return utils.CONFIG_DIR / "loginhistory.json"


def _load_history() -> list:
    p = _loginhistory_file()
    if not p.exists():
        return []
    return json.loads(p.read_text())


def _save_history(logs: list):
    p = _loginhistory_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(logs[-500:], indent=2))


def log_login(username: str, success: bool, ip: str = "", user_agent: str = ""):
    logs = _load_history()
    logs.append({
        "id": len(logs) + 1,
        "username": username,
        "success": success,
        "ip": ip,
        "user_agent": user_agent,
        "timestamp": datetime.datetime.now().isoformat(),
    })
    _save_history(logs)


@router.get("")
def list_login_history(limit: int = Query(50, ge=1, le=500), user: dict = Depends(get_current_user)):
    logs = _load_history()
    return {"history": logs[-limit:][::-1]}
