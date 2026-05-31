"""Public status page API."""

import json
import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/statuspage", tags=["statuspage"])

STATUSPAGE_FILE = utils.CONFIG_DIR / "statuspage.json"


def _load_statuspage() -> dict:
    if STATUSPAGE_FILE.exists():
        with open(STATUSPAGE_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_statuspage(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATUSPAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


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
    data = _load_statuspage()
    config = data.get("config", {})
    incidents = data.get("incidents", [])
    services = data.get("services", [])
    return {
        "title": config.get("title", "System Status"),
        "description": config.get("description", ""),
        "logo_url": config.get("logo_url"),
        "overall_status": "operational",
        "services": services,
        "incidents": [i for i in incidents if not i.get("resolved", False)],
    }


@router.put("/config")
def configure_statuspage(body: StatusPageConfig, user: dict = Depends(get_current_user)):
    data = _load_statuspage()
    data["config"] = {
        "title": body.title,
        "description": body.description,
        "logo_url": body.logo_url,
        "theme": body.theme,
    }
    _save_statuspage(data)
    return {"status": "configured", "config": data["config"]}


@router.post("/incident")
def create_incident(body: IncidentCreate, user: dict = Depends(get_current_user)):
    data = _load_statuspage()
    incidents = data.get("incidents", [])
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    incident_id = str(len(incidents) + 1)
    incident = {
        "id": incident_id,
        "title": body.title,
        "description": body.description,
        "status": body.status,
        "affected_services": body.affected_services,
        "created_at": now,
        "updated_at": now,
        "resolved": False,
        "updates": [{"status": body.status, "message": body.description, "timestamp": now}],
    }
    incidents.append(incident)
    data["incidents"] = incidents
    _save_statuspage(data)
    return {"status": "incident created", "incident": incident}


@router.put("/incident/{incident_id}")
def update_incident(incident_id: str, body: IncidentUpdate, user: dict = Depends(get_current_user)):
    data = _load_statuspage()
    incidents = data.get("incidents", [])
    for inc in incidents:
        if inc["id"] == incident_id:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if body.title is not None:
                inc["title"] = body.title
            if body.description is not None:
                inc["description"] = body.description
            if body.status is not None:
                inc["status"] = body.status
                if body.status == "resolved":
                    inc["resolved"] = True
                inc["updates"].append({
                    "status": body.status,
                    "message": body.description or "",
                    "timestamp": now,
                })
            if body.affected_services is not None:
                inc["affected_services"] = body.affected_services
            inc["updated_at"] = now
            data["incidents"] = incidents
            _save_statuspage(data)
            return {"status": "incident updated", "incident": inc}
    raise HTTPException(status_code=404, detail="Incident not found")
