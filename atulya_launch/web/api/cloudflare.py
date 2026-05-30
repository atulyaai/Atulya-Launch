"""Cloudflare DNS and cache integration API."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/cloudflare", tags=["cloudflare"])

CF_FILE = utils.CONFIG_DIR / "cloudflare.json"


class CloudflareConnect(BaseModel):
    api_key: str
    zone_id: str
    email: Optional[str] = None


class DNSRecordCreate(BaseModel):
    type: str = "A"
    name: str
    content: str
    ttl: int = 1
    proxied: bool = False


def _load_cf() -> dict:
    if CF_FILE.exists():
        import json
        return json.loads(CF_FILE.read_text())
    return {"connected": False, "api_key": "", "zone_id": "", "email": ""}


def _save_cf(data: dict):
    CF_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    CF_FILE.write_text(json.dumps(data, indent=2))


def _cf_headers(data: dict) -> dict:
    return {
        "Authorization": f"Bearer {data['api_key']}",
        "Content-Type": "application/json",
    }


def _cf_request(method: str, endpoint: str, data: dict, json_body: dict = None) -> dict:
    import urllib.request
    import urllib.error
    import json as _json
    url = f"https://api.cloudflare.com/client/v4{endpoint}"
    headers = _cf_headers(data)
    req = urllib.request.Request(url, headers=headers, method=method)
    if json_body:
        req.data = _json.dumps(json_body).encode()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        return {"success": False, "errors": [{"message": body}]}


@router.post("/connect")
def connect_cloudflare(body: CloudflareConnect, user: dict = Depends(get_current_user)):
    test_data = {"api_key": body.api_key, "zone_id": body.zone_id}
    result = _cf_request("GET", f"/zones/{body.zone_id}", test_data)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("errors", [{"message": "Invalid credentials"}]))
    cf_config = {
        "connected": True,
        "api_key": body.api_key,
        "zone_id": body.zone_id,
        "email": body.email or "",
        "zone_name": result.get("result", {}).get("name", ""),
        "connected_at": datetime.datetime.now().isoformat(),
    }
    _save_cf(cf_config)
    return {"status": "connected", "zone_name": cf_config["zone_name"]}


@router.get("/dns")
def list_dns_records(user: dict = Depends(get_current_user)):
    data = _load_cf()
    if not data.get("connected"):
        raise HTTPException(status_code=400, detail="Cloudflare not connected")
    result = _cf_request("GET", f"/zones/{data['zone_id']}/dns_records?per_page=100", data)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=str(result.get("errors")))
    records = []
    for r in result.get("result", []):
        records.append({
            "id": r.get("id"),
            "type": r.get("type"),
            "name": r.get("name"),
            "content": r.get("content"),
            "ttl": r.get("ttl"),
            "proxied": r.get("proxied"),
        })
    return {"records": records}


@router.post("/dns")
def add_dns_record(body: DNSRecordCreate, user: dict = Depends(get_current_user)):
    data = _load_cf()
    if not data.get("connected"):
        raise HTTPException(status_code=400, detail="Cloudflare not connected")
    payload = {
        "type": body.type,
        "name": body.name,
        "content": body.content,
        "ttl": body.ttl,
        "proxied": body.proxied,
    }
    result = _cf_request("POST", f"/zones/{data['zone_id']}/dns_records", data, payload)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("errors")))
    record = result.get("result", {})
    return {"status": "created", "record": {"id": record.get("id"), "name": record.get("name"), "type": record.get("type")}}


@router.delete("/dns/{record_id}")
def delete_dns_record(record_id: str, user: dict = Depends(get_current_user)):
    data = _load_cf()
    if not data.get("connected"):
        raise HTTPException(status_code=400, detail="Cloudflare not connected")
    result = _cf_request("DELETE", f"/zones/{data['zone_id']}/dns_records/{record_id}", data)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("errors")))
    return {"status": "deleted", "record_id": record_id}


@router.post("/purge-cache")
def purge_cache(user: dict = Depends(get_current_user)):
    data = _load_cf()
    if not data.get("connected"):
        raise HTTPException(status_code=400, detail="Cloudflare not connected")
    result = _cf_request("DELETE", f"/zones/{data['zone_id']}/purge_cache", data, {"purge_everything": True})
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("errors")))
    return {"status": "purged", "all_files": True}
