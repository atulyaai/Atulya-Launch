"""Audit trail API — backed by SQLite audit_log table."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Query

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
def list_audit_logs(limit: int = Query(100, ge=1, le=1000), user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, time, user, action, status, details FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    logs = []
    for row in rows:
        entry = dict(row)
        try:
            entry["details"] = json.loads(entry.get("details") or "{}")
        except Exception:
            entry["details"] = {}
        logs.append(entry)
    return {"logs": logs}
