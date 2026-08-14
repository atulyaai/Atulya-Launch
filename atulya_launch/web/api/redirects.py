"""URL redirect management API — backed by SQLite."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/redirects", tags=["redirects"])


class RedirectCreate(BaseModel):
    from_url: str
    to_url: str
    redirect_type: int = 302


class RedirectUpdate(BaseModel):
    to_url: Optional[str] = None
    redirect_type: Optional[int] = None


@router.get("")
def list_redirects(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, domain, from_url, to_url, redirect_type, created_by, created_at FROM redirects ORDER BY id"
        ).fetchall()
    return {"redirects": [dict(r) for r in rows]}


@router.post("")
def create_redirect(body: RedirectCreate, user: dict = Depends(get_current_user)):
    if body.redirect_type not in (301, 302, 307):
        raise HTTPException(status_code=400, detail="Redirect type must be 301, 302, or 307")
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    username = user.get("sub", "admin")
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO redirects (from_url, to_url, redirect_type, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (body.from_url, body.to_url, body.redirect_type, username, now),
        )
        redirect_id = cursor.lastrowid
    return {"status": "created", "id": redirect_id}


@router.delete("/{redirect_id}")
def delete_redirect(redirect_id: int, user: dict = Depends(get_current_user)):
    with connect() as conn:
        cursor = conn.execute("DELETE FROM redirects WHERE id = ?", (redirect_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Redirect not found")
    return {"status": "deleted", "id": redirect_id}


@router.put("/{redirect_id}")
def update_redirect(redirect_id: int, body: RedirectUpdate, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM redirects WHERE id = ?", (redirect_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Redirect not found")
        if body.to_url is not None:
            conn.execute("UPDATE redirects SET to_url = ? WHERE id = ?", (body.to_url, redirect_id))
        if body.redirect_type is not None:
            if body.redirect_type not in (301, 302, 307):
                raise HTTPException(status_code=400, detail="Redirect type must be 301, 302, or 307")
            conn.execute("UPDATE redirects SET redirect_type = ? WHERE id = ?", (body.redirect_type, redirect_id))
    return {"status": "updated", "id": redirect_id}
