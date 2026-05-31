"""Routes for the one-click app installer."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/apps")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def apps_page(request: Request) -> HTMLResponse:
    """Render the apps installer page."""
    installed: dict = core.installed_apps()
    available: dict = core.available_apps()
    return templates.TemplateResponse(request, "apps.html", {
        "user": request.state.user,
        "installed": installed,
        "available": available,
    })


@router.post("/install")
@require_auth
async def app_install(request: Request, app_name: str = Form(...), domain: str = Form(...), db_name: str = Form(""), db_user: str = Form(""), db_pass: str = Form("")) -> RedirectResponse:
    """Install a one-click app."""
    result: dict = core.app_install(app_name, domain, db_name=db_name or None, db_user=db_user or None, db_pass=db_pass or None)
    audit_log(request.state.user["username"], "app.install", "ok" if result.get("ok") else "error", {"app": app_name, "domain": domain})
    return RedirectResponse("/apps", status_code=302)


@router.post("/uninstall")
@require_auth
async def app_uninstall(request: Request, app_name: str = Form(...)) -> RedirectResponse:
    """Uninstall an app."""
    result: dict = core.app_uninstall(app_name)
    audit_log(request.state.user["username"], "app.uninstall", "ok" if result.get("ok") else "error", {"app": app_name})
    return RedirectResponse("/apps", status_code=302)


@router.get("/api/installed")
@require_auth
async def api_installed(request: Request) -> JSONResponse:
    """API endpoint returning installed apps."""
    return JSONResponse(core.installed_apps())


@router.get("/api/available")
@require_auth
async def api_available(request: Request) -> JSONResponse:
    """API endpoint returning available apps from the catalog."""
    return JSONResponse(core.available_apps())
