"""Routes for managing DNS zones and records."""
import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any

from ..auth import require_auth
from ..database import connect, audit_log
from .. import dns_service

router: APIRouter = APIRouter(prefix="/dns")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def dns_list(request: Request) -> HTMLResponse:
    """Render the DNS management page with zones and records."""
    with connect() as cur:
        zones: list[dict] = [dict(r) for r in cur.execute("SELECT * FROM dns_zones ORDER BY domain").fetchall()]
        records: dict[int, list[dict]] = {}
        for zone in zones:
            recs: list[dict] = [dict(r) for r in cur.execute("SELECT * FROM dns_records WHERE zone_id = ?", (zone["id"],)).fetchall()]
            records[zone["id"]] = recs
    return templates.TemplateResponse(request, "dns.html", {
        "user": request.state.user,
        "zones": zones,
        "records": records,
    })


@router.post("/zone/create")
@require_auth
async def zone_create(request: Request, domain: str = Form(...), soa_primary: str = Form("ns1"), soa_email: str = Form("admin")) -> RedirectResponse:
    """Create a new DNS zone."""
    with connect() as cur:
        cur.execute(
            "INSERT INTO dns_zones (domain, soa_primary, soa_email, created_at) VALUES (?, ?, ?, ?)",
            (domain, soa_primary, soa_email, datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"),
        )
    audit_log(request.state.user["username"], "dns.zone_create", "ok", {"domain": domain})
    dns_service.apply_zone(domain)
    return RedirectResponse("/dns", status_code=302)


@router.post("/zone/delete")
@require_auth
async def zone_delete(request: Request, zone_id: int = Form(...)) -> RedirectResponse:
    """Delete a DNS zone and all its records."""
    domain: str | None = None
    with connect() as cur:
        row = cur.execute("SELECT domain FROM dns_zones WHERE id = ?", (zone_id,)).fetchone()
        domain = row["domain"] if row else None
    if domain:
        dns_service.delete_zone(domain)
    audit_log(request.state.user["username"], "dns.zone_delete", "ok", {"zone_id": zone_id, "domain": domain})
    return RedirectResponse("/dns", status_code=302)


@router.post("/record/create")
@require_auth
async def record_create(request: Request, zone_id: int = Form(...), name: str = Form(...), record_type: str = Form("A"), value: str = Form(...), ttl: int = Form(3600)) -> RedirectResponse:
    """Add a DNS record to a zone."""
    with connect() as cur:
        cur.execute(
            "INSERT INTO dns_records (zone_id, name, type, value, ttl, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (zone_id, name, record_type, value, ttl, datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"),
        )
    audit_log(request.state.user["username"], "dns.record_create", "ok", {"zone_id": zone_id, "name": name, "type": record_type})
    with connect() as cur:
        zone = cur.execute("SELECT domain FROM dns_zones WHERE id = ?", (zone_id,)).fetchone()
    if zone:
        dns_service.apply_zone(zone["domain"])
    return RedirectResponse("/dns", status_code=302)


@router.post("/record/delete")
@require_auth
async def record_delete(request: Request, record_id: int = Form(...)) -> RedirectResponse:
    """Delete a DNS record."""
    domain: str | None = None
    with connect() as cur:
        row = cur.execute(
            """
            SELECT z.domain FROM dns_records r
            JOIN dns_zones z ON z.id = r.zone_id
            WHERE r.id = ?
            """,
            (record_id,),
        ).fetchone()
        domain = row["domain"] if row else None
        cur.execute("DELETE FROM dns_records WHERE id = ?", (record_id,))
    audit_log(request.state.user["username"], "dns.record_delete", "ok", {"record_id": record_id})
    if domain:
        dns_service.apply_zone(domain)
    return RedirectResponse("/dns", status_code=302)


@router.get("/api/zones")
@require_auth
async def api_zones(request: Request) -> JSONResponse:
    """API endpoint returning all DNS zones with records."""
    with connect() as cur:
        zones: list[dict] = [dict(r) for r in cur.execute("SELECT * FROM dns_zones").fetchall()]
        for z in zones:
            z["records"] = [dict(r) for r in cur.execute("SELECT * FROM dns_records WHERE zone_id = ?", (z["id"],)).fetchall()]
    return JSONResponse(zones)
