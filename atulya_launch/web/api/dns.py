"""SQLite-backed DNS management API with platform-driver apply support."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web import dns_service

router = APIRouter(prefix="/api/dns", tags=["dns"])


class ZoneCreate(BaseModel):
    domain: str
    nameservers: Optional[list[str]] = None


class RecordCreate(BaseModel):
    type: str
    name: str
    content: str | None = None
    value: str | None = None
    ttl: int = 3600
    priority: Optional[int] = None


class RecordUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    value: Optional[str] = None
    ttl: Optional[int] = None
    priority: Optional[int] = None


@router.get("/zones")
def list_zones(user: dict = Depends(get_current_user)):
    return {"zones": dns_service.list_zones()}


@router.post("/zones")
def create_zone(body: ZoneCreate, user: dict = Depends(get_current_user)):
    try:
        zone = dns_service.create_zone(body.domain, body.nameservers)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Zone already exists")
    return {"zone": zone, "apply": dns_service.apply_zone(body.domain)}


@router.delete("/zones/{zone}")
def delete_zone(zone: str, user: dict = Depends(get_current_user)):
    if not dns_service.delete_zone(zone):
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"status": "deleted", "zone": zone}


@router.get("/zones/{zone}/records")
def list_records(zone: str, user: dict = Depends(get_current_user)):
    try:
        zone_data = dns_service.get_zone(zone)
    except KeyError:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"records": zone_data.get("records", [])}


@router.post("/zones/{zone}/records")
def add_record(zone: str, body: RecordCreate, user: dict = Depends(get_current_user)):
    content = body.content if body.content is not None else body.value
    if not content:
        raise HTTPException(status_code=400, detail="Record content is required")
    try:
        record = dns_service.add_record(zone, body.type, body.name, content, body.ttl)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid record type")
    except KeyError:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"record": record, "apply": dns_service.apply_zone(zone)}


@router.put("/zones/{zone}/records/{record_id}")
def update_record(zone: str, record_id: int, body: RecordUpdate, user: dict = Depends(get_current_user)):
    content = body.content if body.content is not None else body.value
    try:
        record = dns_service.update_record(zone, record_id, name=body.name, value=content, ttl=body.ttl)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"record": record, "apply": dns_service.apply_zone(zone)}


@router.delete("/zones/{zone}/records/{record_id}")
def delete_record(zone: str, record_id: int, user: dict = Depends(get_current_user)):
    try:
        deleted = dns_service.delete_record(zone, record_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Zone not found")
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "deleted", "id": record_id, "apply": dns_service.apply_zone(zone)}


@router.post("/zones/{zone}/reload")
def reload_zone(zone: str, user: dict = Depends(get_current_user)):
    try:
        apply_result = dns_service.apply_zone(zone)
    except KeyError:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"status": "planned" if apply_result["dry_run"] else "applied", "zone": zone, "apply": apply_result}
