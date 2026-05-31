from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log

router = APIRouter(prefix="/backups")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def backups_list(request: Request):
    backups = core.backup_list()
    return templates.TemplateResponse(request, "backups.html", {
        "user": request.state.user,
        "backups": backups,
    })


@router.post("/create")
@require_auth
async def backup_create(request: Request, name: str = Form("")):
    result = core.backup_create(name or None)
    audit_log(request.state.user["username"], "backup.create", "ok", {"name": result["name"]})
    return RedirectResponse("/backups", status_code=302)


@router.post("/restore")
@require_auth
async def backup_restore(request: Request, name: str = Form(...)):
    try:
        result = core.backup_restore(name)
        audit_log(request.state.user["username"], "backup.restore", "ok", {"name": name})
    except ValueError as e:
        audit_log(request.state.user["username"], "backup.restore", "error", {"name": name, "error": str(e)})
    return RedirectResponse("/backups", status_code=302)


@router.get("/api/backups")
@require_auth
async def api_backups(request: Request):
    return JSONResponse(list(core.backup_list().values()))
