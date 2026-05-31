"""Audit trail API."""

import datetime
import json
from typing import Optional
from fastapi import APIRouter, Depends, Query

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _audit_file():
    return utils.CONFIG_DIR / "audit.json"


def _load_audit() -> list:
    p = _audit_file()
    if not p.exists():
        return []
    return json.loads(p.read_text())


def _save_audit(logs: list):
    p = _audit_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(logs[-1000:], indent=2))


def log_audit(action: str, user: str = "admin", details: Optional[dict] = None):
    logs = _load_audit()
    logs.append({
        "id": len(logs) + 1,
        "action": action,
        "user": user,
        "details": details or {},
        "timestamp": datetime.datetime.now().isoformat(),
    })
    _save_audit(logs)


@router.get("/logs")
def list_audit_logs(limit: int = Query(100, ge=1, le=1000), user: dict = Depends(get_current_user)):
    logs = _load_audit()
    return {"logs": logs[-limit:][::-1]}
