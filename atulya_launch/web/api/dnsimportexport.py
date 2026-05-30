"""DNS Zone Import/Export API."""

import json
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/dns", tags=["dns-import-export"])

ZONES_DIR = utils.CONFIG_DIR / "dns" / "zones"


def _ensure_zones_dir():
    ZONES_DIR.mkdir(parents=True, exist_ok=True)


def _zone_file_path(zone: str) -> str:
    return str(ZONES_DIR / f"{zone}.zone")


def _zone_json_path(zone: str) -> str:
    return str(ZONES_DIR / f"{zone}.json")


def _load_zone_json(zone: str) -> dict:
    p = _zone_json_path(zone)
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return json.load(f) or {}


def _save_zone_json(zone: str, data: dict):
    _ensure_zones_dir()
    with open(_zone_json_path(zone), "w") as f:
        json.dump(data, f, indent=2)


def _record_to_bind_line(rec: dict) -> str:
    parts = []
    name = rec.get("name", "@")
    ttl = rec.get("ttl", 3600)
    rtype = rec.get("type", "A")
    priority = rec.get("priority")
    content = rec.get("content", "")

    if priority is not None and rtype in ("MX", "SRV"):
        parts.append(f"{name}\tIN\t{rtype}\t{priority}\t{content}")
    else:
        parts.append(f"{name}\tIN\t{rtype}\t{content}")
    return parts[0]


def _generate_zone_file(zone: str, zone_data: dict) -> str:
    ns_list = zone_data.get("nameservers", [f"ns1.{zone}", f"ns2.{zone}"])
    records = zone_data.get("records", [])
    serial = zone_data.get("serial", 1)

    lines = [
        f"$TTL 3600",
        f"@ IN SOA {ns_list[0]}. admin.{zone}. (",
        f"    {serial}        ; serial",
        f"    3600            ; refresh",
        f"    900             ; retry",
        f"    604800          ; expiry",
        f"    86400           ; minimum",
        f")",
        "",
    ]

    for ns in ns_list:
        lines.append(f"@ IN NS {ns}.")

    lines.append("")

    for rec in records:
        lines.append(_record_to_bind_line(rec))

    return "\n".join(lines) + "\n"


def _parse_bind_zone(content: str, zone_name: str) -> dict:
    records = []
    nameservers = []
    serial = 1

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("$") or line.startswith(";"):
            continue
        if line.startswith("(") or line.startswith(")"):
            continue

        parts = line.split()
        if len(parts) < 4:
            continue

        if "SOA" in parts:
            soa_match = re.search(r"SOA\s+(\S+)\s+(\S+)", line)
            if soa_match:
                nameservers.append(soa_match.group(1).rstrip("."))
            serial_match = re.search(r"(\d+)\s*;\s*serial", content[content.index(line):content.index(line) + 200])
            if serial_match:
                serial = int(serial_match.group(1))
            continue

        if "NS" in parts:
            ns_match = re.search(r"NS\s+(\S+)", line)
            if ns_match:
                ns = ns_match.group(1).rstrip(".")
                if ns not in nameservers:
                    nameservers.append(ns)
            continue

        name = parts[0] if parts[0] != "@" else zone_name
        rtype = None
        priority = None
        content_val = ""

        idx = 1
        if parts[idx] == "IN":
            idx += 1
        if idx >= len(parts):
            continue

        rtype = parts[idx]
        idx += 1

        if rtype in ("MX", "SRV") and idx < len(parts):
            try:
                priority = int(parts[idx])
                idx += 1
            except ValueError:
                pass

        content_val = " ".join(parts[idx:])
        content_val = content_val.rstrip(".")

        if rtype in ("A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "PTR"):
            rec = {
                "id": len(records) + 1,
                "type": rtype,
                "name": name if name != zone_name else "@",
                "content": content_val,
                "ttl": 3600,
            }
            if priority is not None:
                rec["priority"] = priority
            records.append(rec)

    if not nameservers:
        nameservers = [f"ns1.{zone_name}", f"ns2.{zone_name}"]

    return {
        "domain": zone_name,
        "nameservers": nameservers,
        "records": records,
        "serial": serial,
        "imported_at": datetime.now().isoformat(),
    }


class ZoneImport(BaseModel):
    zone: str
    content: str


@router.get("/zones/{zone}/export")
def export_zone(zone: str, user: dict = Depends(get_current_user)):
    _ensure_zones_dir()
    zone_data = _load_zone_json(zone)
    if not zone_data:
        raise HTTPException(status_code=404, detail="Zone not found")

    bind_content = _generate_zone_file(zone, zone_data)
    _ensure_zones_dir()
    export_path = ZONES_DIR / f"{zone}_export.zone"
    with open(export_path, "w") as f:
        f.write(bind_content)

    return PlainTextResponse(
        content=bind_content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{zone}.zone"'},
    )


@router.post("/zones/import")
def import_zone(body: ZoneImport, user: dict = Depends(get_current_user)):
    _ensure_zones_dir()

    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Zone content cannot be empty")

    parsed = _parse_bind_zone(body.content, body.zone)
    existing = _load_zone_json(body.zone)

    if existing:
        existing_records = existing.get("records", [])
        max_id = max((r.get("id", 0) for r in existing_records), default=0)
        for rec in parsed["records"]:
            max_id += 1
            rec["id"] = max_id
        parsed["records"] = existing_records + parsed["records"]
        parsed["serial"] = existing.get("serial", 1) + 1

    _save_zone_json(body.zone, parsed)

    bind_file = ZONES_DIR / f"{body.zone}.zone"
    with open(bind_file, "w") as f:
        f.write(_generate_zone_file(body.zone, parsed))

    utils.run_command(["rndc", "reload", body.zone], check=False)

    return {
        "status": "imported",
        "zone": body.zone,
        "records_imported": len(parsed["records"]),
        "nameservers": parsed["nameservers"],
    }


@router.get("/zones/{zone}/export/raw")
def export_zone_raw(zone: str, user: dict = Depends(get_current_user)):
    _ensure_zones_dir()
    zone_data = _load_zone_json(zone)
    if not zone_data:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"zone_file": _generate_zone_file(zone, zone_data)}
