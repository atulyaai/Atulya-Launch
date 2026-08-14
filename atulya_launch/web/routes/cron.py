"""Routes for cron job management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth

router: APIRouter = APIRouter(prefix="/cron")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def cron_page(request: Request) -> HTMLResponse:
    """Render the cron jobs management page."""
    jobs: list[dict] = core.cron_list()
    return templates.TemplateResponse(request, "cron.html", {
        "user": request.state.user,
        "jobs": jobs,
    })


@router.post("/create")
@require_auth
async def cron_create(request: Request, command: str = Form(...), schedule: str = Form("0 0 * * *"), domain: str = Form("")) -> RedirectResponse:
    """Create a new cron job."""
    core.cron_create(request.state.user["id"], command, schedule, domain=domain or None)
    return RedirectResponse("/cron", status_code=302)


@router.post("/delete")
@require_auth
async def cron_delete(request: Request, job_id: int = Form(...)) -> RedirectResponse:
    """Delete a cron job."""
    core.cron_delete(job_id)
    return RedirectResponse("/cron", status_code=302)


@router.post("/toggle")
@require_auth
async def cron_toggle(request: Request, job_id: int = Form(...), enabled: int = Form(1)) -> RedirectResponse:
    """Enable or disable a cron job."""
    core.cron_toggle(job_id, enabled)
    return RedirectResponse("/cron", status_code=302)


@router.get("/api/list")
@require_auth
async def api_list(request: Request) -> JSONResponse:
    """API endpoint returning all cron jobs."""
    return JSONResponse(core.cron_list())
