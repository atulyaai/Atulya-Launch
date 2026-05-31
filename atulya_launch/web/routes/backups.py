"""Routes for managing backups and backup schedules."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log
from .. import backup_service

router: APIRouter = APIRouter(prefix="/backups")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def backups_list(request: Request) -> HTMLResponse:
    """Render the backups management page."""
    backups: dict = backup_service.list_backups()
    schedules: list[dict] = core.backup_schedule_list()
    from .. import sites_service
    domains: list[str] = list(sites_service.list_sites().keys())
    return templates.TemplateResponse(request, "backups.html", {
        "user": request.state.user,
        "backups": backups,
        "schedules": schedules,
        "domains": domains,
    })


@router.post("/create")
@require_auth
async def backup_create(request: Request, name: str = Form("")) -> RedirectResponse:
    """Create a new backup."""
    result: dict = backup_service.create_backup(name or None)
    audit_log(request.state.user["username"], "backup.create", "ok", {"name": result["name"]})
    return RedirectResponse("/backups", status_code=302)


@router.post("/restore")
@require_auth
async def backup_restore(request: Request, name: str = Form(...)) -> RedirectResponse:
    """Restore from a backup."""
    try:
        result: dict = backup_service.restore_backup(name)
        audit_log(request.state.user["username"], "backup.restore", "ok", {"name": name})
    except ValueError as e:
        audit_log(request.state.user["username"], "backup.restore", "error", {"name": name, "error": str(e)})
    return RedirectResponse("/backups", status_code=302)


@router.post("/schedule/create")
@require_auth
async def backup_schedule_create(request: Request, domain: str = Form(...), schedule_type: str = Form("daily"), retention: int = Form(7), time_str: str = Form("02:00")) -> RedirectResponse:
    """Create a scheduled backup."""
    result: dict = core.backup_schedule_create(domain, schedule_type, retention, time_str)
    status: str = "ok" if result.get("ok") else "error"
    audit_log(request.state.user["username"], "backup.schedule.create", status, {"domain": domain, "schedule": schedule_type})
    return RedirectResponse("/backups", status_code=302)


@router.post("/schedule/delete")
@require_auth
async def backup_schedule_delete(request: Request, schedule_id: int = Form(...)) -> RedirectResponse:
    """Delete a backup schedule."""
    core.backup_schedule_delete(schedule_id)
    audit_log(request.state.user["username"], "backup.schedule.delete", "ok", {"id": schedule_id})
    return RedirectResponse("/backups", status_code=302)


@router.post("/run-now")
@require_auth
async def backup_run_now(request: Request, domain: str = Form(...)) -> RedirectResponse:
    """Run an immediate backup for a domain."""
    result: dict = core.backup_run_now(domain)
    audit_log(request.state.user["username"], "backup.run", "ok" if result.get("ok") else "error", {"domain": domain})
    return RedirectResponse("/backups", status_code=302)


@router.get("/api/backups")
@require_auth
async def api_backups(request: Request) -> JSONResponse:
    """API endpoint returning all backups."""
    return JSONResponse(list(backup_service.list_backups().values()))
