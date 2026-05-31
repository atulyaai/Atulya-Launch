"""API token management — backed by SQLite."""

import json
import secrets
import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


class TokenCreate(BaseModel):
    name: str
    permissions: List[str] = ["read"]
    expires_days: Optional[int] = 30


@router.get("")
def list_tokens(user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    with connect() as conn:
        rows = conn.execute(
            "SELECT token_id, name, permissions, created_by, created_at, expires_at, last_used FROM api_tokens WHERE created_by = ? ORDER BY id DESC",
            (username,),
        ).fetchall()
    tokens = []
    for row in rows:
        entry = dict(row)
        expired = False
        if entry.get("expires_at"):
            try:
                exp = datetime.datetime.fromisoformat(entry["expires_at"])
                expired = exp < datetime.datetime.now(datetime.timezone.utc)
            except Exception:
                pass
        entry["expired"] = expired
        try:
            entry["permissions"] = json.loads(entry.get("permissions") or "[]")
        except Exception:
            entry["permissions"] = ["read"]
        tokens.append(entry)
    return {"tokens": tokens}


@router.post("")
def create_token(body: TokenCreate, user: dict = Depends(get_current_user)):
    token_value = secrets.token_hex(32)
    token_id = token_value[:16]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    expires_at = None
    if body.expires_days:
        expires_at = (now + datetime.timedelta(days=body.expires_days)).isoformat() if isinstance(now, str) else None
        if isinstance(now, str):
            expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=body.expires_days)).isoformat()
    username = user.get("sub", "admin")
    with connect() as conn:
        conn.execute(
            "INSERT INTO api_tokens (token_id, name, token_hash, permissions, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token_id, body.name, token_value, json.dumps(body.permissions), username, now, expires_at),
        )
    return {
        "status": "token created",
        "id": token_id,
        "token": token_value,
        "name": body.name,
        "expires_at": expires_at,
        "message": "Save this token. It will not be shown again.",
    }


@router.delete("/{token_id}")
def revoke_token(token_id: str, user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM api_tokens WHERE token_id = ? AND created_by = ?",
            (token_id, username),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Token not found")
        conn.execute("DELETE FROM api_tokens WHERE token_id = ?", (token_id,))
    return {"status": "revoked", "id": token_id}
