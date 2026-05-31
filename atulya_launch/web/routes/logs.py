"""Routes for viewing system and panel logs."""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth

router: APIRouter = APIRouter(prefix="/logs")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def logs_page(request: Request) -> HTMLResponse:
    """Render the log viewer page."""
    sources: list[dict] = core.log_list_sources()
    return templates.TemplateResponse(request, "logs.html", {
        "user": request.state.user,
        "sources": sources,
    })


@router.get("/view")
@require_auth
async def logs_view(request: Request, source: str = "nginx_access", lines: int = Query(100, ge=10, le=5000), grep: str = Query("")) -> JSONResponse:
    """View log file contents."""
    result: dict = core.log_view(source, lines=lines, grep=grep or None)
    return JSONResponse(result)
