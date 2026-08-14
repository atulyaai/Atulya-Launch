"""Routes for Node.js/Python app deployment."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth

router: APIRouter = APIRouter(prefix="/deploy")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def deploy_page(request: Request) -> HTMLResponse:
    """Render the app deployment page."""
    apps: list[dict] = core.deploy_list()
    return templates.TemplateResponse(request, "deploy.html", {
        "user": request.state.user,
        "apps": apps,
    })


@router.post("/create")
@require_auth
async def deploy_create(request: Request, name: str = Form(...), domain: str = Form(...), app_type: str = Form("node"), entry_point: str = Form("index.js"), port: int = Form(3000)) -> RedirectResponse:
    """Create a new deployable app."""
    core.deploy_app(name, domain, app_type, entry_point, port)
    return RedirectResponse("/deploy", status_code=302)


@router.post("/delete")
@require_auth
async def deploy_delete(request: Request, app_id: int = Form(...)) -> RedirectResponse:
    """Delete a deployed app."""
    core.deploy_delete(app_id)
    return RedirectResponse("/deploy", status_code=302)


@router.post("/start")
@require_auth
async def deploy_start(request: Request, app_id: int = Form(...)) -> RedirectResponse:
    """Start a deployed app."""
    core.deploy_start(app_id)
    return RedirectResponse("/deploy", status_code=302)


@router.post("/stop")
@require_auth
async def deploy_stop(request: Request, app_id: int = Form(...)) -> RedirectResponse:
    """Stop a deployed app."""
    core.deploy_stop(app_id)
    return RedirectResponse("/deploy", status_code=302)


@router.get("/api/list")
@require_auth
async def api_list(request: Request) -> JSONResponse:
    """API endpoint returning all deployed apps."""
    return JSONResponse(core.deploy_list())
