"""Cloud DNS Provider Integration API — Cloudflare, Route53, Google DNS."""

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/dns/providers", tags=["cloud-dns"])

PROVIDERS_FILE = utils.CONFIG_DIR / "dns_providers.json"
CREDENTIALS_DIR = utils.CONFIG_DIR / "dns_credentials"


def _ensure_credentials_dir():
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)


def _load_providers() -> dict:
    if PROVIDERS_FILE.exists():
        with open(PROVIDERS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_providers(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROVIDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _fetch_cloudflare_zones(api_token: str) -> list:
    result = utils.run_command(
        ["curl", "-s", "-H", f"Authorization: Bearer {api_token}", "https://api.cloudflare.com/client/v4/zones"],
        check=False,
    )
    if not result or result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        if data.get("success"):
            return [{"id": z["id"], "name": z["name"], "status": z["status"]} for z in data.get("result", [])]
    except (json.JSONDecodeError, KeyError):
        pass
    return []


def _fetch_cloudflare_records(zone_id: str, api_token: str) -> list:
    result = utils.run_command(
        ["curl", "-s", "-H", f"Authorization: Bearer {api_token}", f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"],
        check=False,
    )
    if not result or result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        if data.get("success"):
            records = []
            for r in data.get("result", []):
                records.append({
                    "id": r["id"],
                    "type": r["type"],
                    "name": r["name"],
                    "content": r["content"],
                    "ttl": r.get("ttl", 1),
                    "proxied": r.get("proxied", False),
                })
            return records
    except (json.JSONDecodeError, KeyError):
        pass
    return []


def _fetch_route53_zones(profile: Optional[str] = None) -> list:
    cmd = ["aws", "route53", "list-hosted-zones", "--output", "json"]
    if profile:
        cmd = ["aws", "--profile", profile, "route53", "list-hosted-zones", "--output", "json"]
    result = utils.run_command(cmd, check=False)
    if not result or result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        zones = []
        for z in data.get("HostedZones", []):
            zones.append({
                "id": z["Id"].split("/")[-1],
                "name": z["Name"].rstrip("."),
                "private": z.get("PrivateZone", False),
            })
        return zones
    except (json.JSONDecodeError, KeyError):
        return []


def _fetch_route53_records(zone_id: str, profile: Optional[str] = None) -> list:
    cmd = ["aws", "route53", "list-resource-record-sets", "--hosted-zone-id", zone_id, "--output", "json"]
    if profile:
        cmd = ["aws", "--profile", profile, "route53", "list-resource-record-sets", "--hosted-zone-id", zone_id, "--output", "json"]
    result = utils.run_command(cmd, check=False)
    if not result or result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        records = []
        for r in data.get("ResourceRecordSets", []):
            values = [rr["Value"] for rr in r.get("ResourceRecords", [])]
            records.append({
                "type": r["Type"],
                "name": r["Name"].rstrip("."),
                "ttl": r.get("TTL"),
                "values": values,
            })
        return records
    except (json.JSONDecodeError, KeyError):
        return []


def _fetch_google_zones(credentials_file: str) -> list:
    result = utils.run_command(
        ["gcloud", "dns", "managed-zones", "list", "--format=json", f"--project={Path(credentials_file).stem}"],
        check=False,
    )
    if not result or result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        return [{"id": z.get("name", ""), "name": z.get("dnsName", "").rstrip("."), "description": z.get("description", "")} for z in data]
    except (json.JSONDecodeError, KeyError):
        return []


def _fetch_google_records(zone_name: str, project: str) -> list:
    result = utils.run_command(
        ["gcloud", "dns", "record-sets", "list", "--zone", zone_name, "--format=json", f"--project={project}"],
        check=False,
    )
    if not result or result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        return [{"type": r["type"], "name": r["name"].rstrip("."), "ttl": r.get("ttl"), "rrdatas": r.get("rrdatas", [])} for r in data]
    except (json.JSONDecodeError, KeyError):
        return []


class CloudflareProvider(BaseModel):
    provider_type: str = "cloudflare"
    name: str
    api_token: str


class Route53Provider(BaseModel):
    provider_type: str = "route53"
    name: str
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_profile: Optional[str] = None
    region: str = "us-east-1"


class GoogleDNSProvider(BaseModel):
    provider_type: str = "google"
    name: str
    credentials_file: str
    project: str


@router.get("")
def list_providers(user: dict = Depends(get_current_user)):
    providers = _load_providers()
    safe = {}
    for k, v in providers.items():
        safe_v = {**v}
        if "api_token" in safe_v:
            safe_v["api_token"] = safe_v["api_token"][:8] + "..."
        if "aws_secret_key" in safe_v:
            safe_v["aws_secret_key"] = "***"
        safe[k] = safe_v
    return {"providers": safe}


@router.post("")
def add_provider(body: CloudflareProvider | Route53Provider | GoogleDNSProvider, user: dict = Depends(get_current_user)):
    providers = _load_providers()
    provider_id = str(uuid.uuid4())[:8]

    if body.provider_type == "cloudflare":
        zones = _fetch_cloudflare_zones(body.api_token)
        if not zones:
            raise HTTPException(status_code=400, detail="Could not fetch Cloudflare zones. Check API token.")
        providers[provider_id] = {
            "id": provider_id,
            "provider_type": "cloudflare",
            "name": body.name,
            "api_token": body.api_token,
            "zones": zones,
            "created_at": datetime.now().isoformat(),
        }

    elif body.provider_type == "route53":
        _ensure_credentials_dir()
        if body.aws_access_key and body.aws_secret_key:
            creds_path = CREDENTIALS_DIR / f"{provider_id}_aws.json"
            creds = {
                "access_key": body.aws_access_key,
                "secret_key": body.aws_secret_key,
                "region": body.region,
            }
            creds_path.write_text(json.dumps(creds))
        zones = _fetch_route53_zones(body.aws_profile)
        providers[provider_id] = {
            "id": provider_id,
            "provider_type": "route53",
            "name": body.name,
            "aws_profile": body.aws_profile,
            "region": body.region,
            "has_credentials": bool(body.aws_access_key),
            "zones": zones,
            "created_at": datetime.now().isoformat(),
        }

    elif body.provider_type == "google":
        if not Path(body.credentials_file).exists():
            raise HTTPException(status_code=400, detail="Credentials file not found")
        zones = _fetch_google_zones(body.credentials_file)
        providers[provider_id] = {
            "id": provider_id,
            "provider_type": "google",
            "name": body.name,
            "credentials_file": body.credentials_file,
            "project": body.project,
            "zones": zones,
            "created_at": datetime.now().isoformat(),
        }

    else:
        raise HTTPException(status_code=400, detail="provider_type must be cloudflare, route53, or google")

    _save_providers(providers)
    return {"status": "added", "provider_id": provider_id, "zones": providers[provider_id].get("zones", [])}


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, user: dict = Depends(get_current_user)):
    providers = _load_providers()
    if provider_id not in providers:
        raise HTTPException(status_code=404, detail="Provider not found")
    del providers[provider_id]
    _save_providers(providers)
    return {"status": "deleted", "provider_id": provider_id}


@router.post("/{provider_id}/sync")
def sync_provider(provider_id: str, user: dict = Depends(get_current_user)):
    providers = _load_providers()
    if provider_id not in providers:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider = providers[provider_id]
    ptype = provider.get("provider_type")

    if ptype == "cloudflare":
        zones = _fetch_cloudflare_zones(provider["api_token"])
        provider["zones"] = zones
        for zone in zones:
            records = _fetch_cloudflare_records(zone["id"], provider["api_token"])
            zone["records"] = records

    elif ptype == "route53":
        profile = provider.get("aws_profile")
        zones = _fetch_route53_zones(profile)
        provider["zones"] = zones
        for zone in zones:
            records = _fetch_route53_records(zone["id"], profile)
            zone["records"] = records

    elif ptype == "google":
        project = provider.get("project", "")
        zones = _fetch_google_zones(provider.get("credentials_file", ""))
        provider["zones"] = zones
        for zone in zones:
            records = _fetch_google_records(zone["id"], project)
            zone["records"] = records

    provider["last_synced"] = datetime.now().isoformat()
    providers[provider_id] = provider
    _save_providers(providers)

    return {
        "status": "synced",
        "provider_id": provider_id,
        "zones": provider.get("zones", []),
    }


@router.get("/{provider_id}/zones")
def list_provider_zones(provider_id: str, user: dict = Depends(get_current_user)):
    providers = _load_providers()
    if provider_id not in providers:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"zones": providers[provider_id].get("zones", [])}


@router.get("/{provider_id}/zones/{zone_id}/records")
def list_zone_records(provider_id: str, zone_id: str, user: dict = Depends(get_current_user)):
    providers = _load_providers()
    if provider_id not in providers:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider = providers[provider_id]
    ptype = provider.get("provider_type")

    if ptype == "cloudflare":
        records = _fetch_cloudflare_records(zone_id, provider["api_token"])
    elif ptype == "route53":
        records = _fetch_route53_records(zone_id, provider.get("aws_profile"))
    elif ptype == "google":
        records = _fetch_google_records(zone_id, provider.get("project", ""))
    else:
        records = []

    return {"provider_id": provider_id, "zone_id": zone_id, "records": records}
