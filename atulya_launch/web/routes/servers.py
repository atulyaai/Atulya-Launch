"""Routes for remote server management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth, require_admin
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/servers")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_admin
async def servers_page(request: Request) -> HTMLResponse:
    """Render the remote servers management page."""
    servers: list[dict] = core.server_list()
    return templates.TemplateResponse(request, "servers.html", {
        "user": request.state.user,
        "servers": servers,
    })


@router.post("/create")
@require_admin
async def server_create(request: Request, name: str = Form(...), host: str = Form(...), port: int = Form(22), username: str = Form("root"), auth_type: str = Form("password"), auth_data: str = Form("")) -> RedirectResponse:
    """Add a new remote server."""
    core.server_create(name, host, port, username, auth_type, auth_data)
    return RedirectResponse("/servers", status_code=302)


@router.post("/delete")
@require_admin
async def server_delete(request: Request, server_id: int = Form(...)) -> RedirectResponse:
    """Delete a remote server."""
    core.server_delete(server_id)
    return RedirectResponse("/servers", status_code=302)


@router.post("/exec")
@require_admin
async def server_exec(request: Request, server_id: int = Form(...), command: str = Form(...)) -> JSONResponse:
    """Execute a command on a remote server via SSH."""
    result: dict = core.server_exec(server_id, command)
    audit_log(request.state.user["username"], "server.exec", "ok" if result.get("ok") else "error", {"server_id": server_id, "command": command[:60]})
    return JSONResponse(result)


@router.get("/api/list")
@require_auth
async def api_list(request: Request) -> JSONResponse:
    """API endpoint returning all remote servers."""
    return JSONResponse(core.server_list())
