"""Public status page API."""

import json
import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/statuspage", tags=["statuspage"])


def _load_config() -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM statuspage_config").fetchall()
    config = {}
    for r in rows:
        try:
            config[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            config[r["key"]] = r["value"]
    return config


def _save_config(data: dict):
    with connect() as conn:
        for key, value in data.items():
            conn.execute(
                "INSERT OR REPLACE INTO statuspage_config (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )


class StatusPageConfig(BaseModel):
    title: str = "System Status"
    description: str = ""
    logo_url: Optional[str] = None
    theme: str = "light"


class IncidentCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "investigating"
    affected_services: List[str] = []


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    affected_services: Optional[List[str]] = None


@router.get("")
def get_public_status():
    """Public endpoint - no auth required."""
    config = _load_config()
    with connect() as conn:
        services_rows = conn.execute("SELECT value FROM statuspage_config WHERE key = 'services'").fetchone()
        services = json.loads(services_rows["value"]) if services_rows else []
        incident_rows = conn.execute(
            "SELECT incident_id, title, description, status, affected_services, resolved, updates_json, created_at, updated_at FROM statuspage_incidents WHERE resolved = 0 ORDER BY created_at DESC"
        ).fetchall()
    incidents = []
    for r in incident_rows:
        incidents.append({
            "id": r["incident_id"],
            "title": r["title"],
            "description": r["description"],
            "status": r["status"],
            "affected_services": json.loads(r["affected_services"]),
            "resolved": bool(r["resolved"]),
            "updates": json.loads(r["updates_json"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return {
        "title": config.get("title", "System Status"),
        "description": config.get("description", ""),
        "logo_url": config.get("logo_url"),
        "overall_status": "operational",
        "services": services,
        "incidents": incidents,
    }


@router.put("/config")
def configure_statuspage(body: StatusPageConfig, user: dict = Depends(get_current_user)):
    _save_config({
        "title": body.title,
        "description": body.description,
        "logo_url": body.logo_url,
        "theme": body.theme,
    })
    return {"status": "configured", "config": {
        "title": body.title,
        "description": body.description,
        "logo_url": body.logo_url,
        "theme": body.theme,
    }}


@router.post("/incident")
def create_incident(body: IncidentCreate, user: dict = Depends(get_current_user)):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    incident_id = str(int(now.timestamp()))
    updates = [{"status": body.status, "message": body.description, "timestamp": now}]
    with connect() as conn:
        conn.execute(
            """INSERT INTO statuspage_incidents
               (incident_id, title, description, status, affected_services, resolved, updates_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (incident_id, body.title, body.description, body.status,
             json.dumps(body.affected_services), json.dumps(updates), now, now),
        )
    incident = {
        "id": incident_id,
        "title": body.title,
        "description": body.description,
        "status": body.status,
        "affected_services": body.affected_services,
        "created_at": now,
        "updated_at": now,
        "resolved": False,
        "updates": updates,
    }
    return {"status": "incident created", "incident": incident}


@router.put("/incident/{incident_id}")
def update_incident(incident_id: str, body: IncidentUpdate, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM statuspage_incidents WHERE incident_id = ?", (incident_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updates = json.loads(row["updates_json"])
        title = body.title if body.title is not None else row["title"]
        description = body.description if body.description is not None else row["description"]
        status = body.status if body.status is not None else row["status"]
        affected = json.dumps(body.affected_services) if body.affected_services is not None else row["affected_services"]
        resolved = row["resolved"]
        if body.status == "resolved":
            resolved = 1
        if body.status is not None:
            updates.append({"status": body.status, "message": body.description or "", "timestamp": now})
        conn.execute(
            """UPDATE statuspage_incidents
               SET title = ?, description = ?, status = ?, affected_services = ?, resolved = ?, updates_json = ?, updated_at = ?
               WHERE incident_id = ?""",
            (title, description, status, affected, resolved, json.dumps(updates), now, incident_id),
        )
    incident = {
        "id": incident_id,
        "title": title,
        "description": description,
        "status": status,
        "affected_services": json.loads(affected),
        "resolved": bool(resolved),
        "updates": updates,
        "created_at": row["created_at"],
        "updated_at": now,
    }
    return {"status": "incident updated", "incident": incident}
