"""DNS management API (BIND9)."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/dns", tags=["dns"])


class ZoneCreate(BaseModel):
    domain: str
    nameservers: Optional[list[str]] = None


class RecordCreate(BaseModel):
    type: str
    name: str
    content: str
    ttl: int = 3600
    priority: Optional[int] = None


class RecordUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    ttl: Optional[int] = None
    priority: Optional[int] = None


def _zones_file():
    return utils.CONFIG_DIR / "dns" / "zones.json"


def _load_zones() -> dict:
    p = _zones_file()
    if not p.exists():
        return {}
    import json
    return json.loads(p.read_text())


def _save_zones(zones: dict):
    p = _zones_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(zones, indent=2))


def _next_record_id(records: list) -> int:
    if not records:
        return 1
    return max(r.get("id", 0) for r in records) + 1


@router.get("/zones")
def list_zones(user: dict = Depends(get_current_user)):
    return {"zones": _load_zones()}


@router.post("/zones")
def create_zone(body: ZoneCreate, user: dict = Depends(get_current_user)):
    zones = _load_zones()
    if body.domain in zones:
        raise HTTPException(status_code=409, detail="Zone already exists")
    ns = body.nameservers or [f"ns1.{body.domain}", f"ns2.{body.domain}"]
    zones[body.domain] = {
        "domain": body.domain,
        "nameservers": ns,
        "records": [],
        "created_at": utils.datetime.datetime.now().isoformat() if hasattr(utils, "datetime") else __import__("datetime").datetime.now().isoformat(),
    }
    _save_zones(zones)
    return {"zone": zones[body.domain]}


@router.get("/zones/{zone}/records")
def list_records(zone: str, user: dict = Depends(get_current_user)):
    zones = _load_zones()
    if zone not in zones:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"records": zones[zone].get("records", [])}


@router.post("/zones/{zone}/records")
def add_record(zone: str, body: RecordCreate, user: dict = Depends(get_current_user)):
    zones = _load_zones()
    if zone not in zones:
        raise HTTPException(status_code=404, detail="Zone not found")
    if body.type not in ("A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "PTR"):
        raise HTTPException(status_code=400, detail="Invalid record type")
    records = zones[zone].get("records", [])
    rec = {
        "id": _next_record_id(records),
        "type": body.type,
        "name": body.name,
        "content": body.content,
        "ttl": body.ttl,
    }
    if body.priority is not None:
        rec["priority"] = body.priority
    records.append(rec)
    zones[zone]["records"] = records
    _save_zones(zones)
    return {"record": rec}


@router.put("/zones/{zone}/records/{record_id}")
def update_record(zone: str, record_id: int, body: RecordUpdate, user: dict = Depends(get_current_user)):
    zones = _load_zones()
    if zone not in zones:
        raise HTTPException(status_code=404, detail="Zone not found")
    records = zones[zone].get("records", [])
    for rec in records:
        if rec.get("id") == record_id:
            if body.name is not None:
                rec["name"] = body.name
            if body.content is not None:
                rec["content"] = body.content
            if body.ttl is not None:
                rec["ttl"] = body.ttl
            if body.priority is not None:
                rec["priority"] = body.priority
            _save_zones(zones)
            return {"record": rec}
    raise HTTPException(status_code=404, detail="Record not found")


@router.delete("/zones/{zone}/records/{record_id}")
def delete_record(zone: str, record_id: int, user: dict = Depends(get_current_user)):
    zones = _load_zones()
    if zone not in zones:
        raise HTTPException(status_code=404, detail="Zone not found")
    records = zones[zone].get("records", [])
    zones[zone]["records"] = [r for r in records if r.get("id") != record_id]
    if len(zones[zone]["records"]) == len(records):
        raise HTTPException(status_code=404, detail="Record not found")
    _save_zones(zones)
    return {"status": "deleted", "id": record_id}


@router.post("/zones/{zone}/reload")
def reload_zone(zone: str, user: dict = Depends(get_current_user)):
    zones = _load_zones()
    if zone not in zones:
        raise HTTPException(status_code=404, detail="Zone not found")
    result = utils.run_command(["rndc", "reload", zone], check=False)
    if result and result.returncode == 0:
        return {"status": "reloaded", "zone": zone}
    return {"status": "reload_sent", "zone": zone, "note": "rndc may not be available"}
