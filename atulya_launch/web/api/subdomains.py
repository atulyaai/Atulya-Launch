"""Subdomain management API — backed by SQLite."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/subdomains", tags=["subdomains"])


class SubdomainCreate(BaseModel):
    domain: str
    subdomain: str
    target: str


class SubdomainUpdate(BaseModel):
    target: Optional[str] = None
    subdomain: Optional[str] = None


@router.get("")
def list_subdomains(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, domain, subdomain, target, created_by, created_at FROM subdomains ORDER BY id"
        ).fetchall()
    return {"subdomains": [dict(r) for r in rows]}


@router.post("")
def create_subdomain(body: SubdomainCreate, user: dict = Depends(get_current_user)):
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    username = user.get("sub", "admin")
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO subdomains (domain, subdomain, target, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (body.domain, body.subdomain, body.target, username, now),
            )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=400, detail="Subdomain already exists")
        raise
    return {"status": "created", "domain": body.domain, "subdomain": body.subdomain}


@router.delete("/{subdomain_id}")
def delete_subdomain(subdomain_id: int, user: dict = Depends(get_current_user)):
    with connect() as conn:
        cursor = conn.execute("DELETE FROM subdomains WHERE id = ?", (subdomain_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Subdomain not found")
    return {"status": "deleted", "id": subdomain_id}


@router.put("/{subdomain_id}")
def update_subdomain(subdomain_id: int, body: SubdomainUpdate, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM subdomains WHERE id = ?", (subdomain_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subdomain not found")
        if body.target is not None:
            conn.execute("UPDATE subdomains SET target = ? WHERE id = ?", (body.target, subdomain_id))
        if body.subdomain is not None:
            conn.execute("UPDATE subdomains SET subdomain = ? WHERE id = ?", (body.subdomain, subdomain_id))
    return {"status": "updated", "id": subdomain_id}
