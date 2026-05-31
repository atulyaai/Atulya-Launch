"""Routes for the in-browser SSH terminal."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ..auth import require_auth

router: APIRouter = APIRouter(prefix="/ssh-terminal")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def ssh_terminal_page(request: Request) -> HTMLResponse:
    """Render the xterm.js SSH terminal page."""
    return templates.TemplateResponse(request, "ssh_terminal.html", {"user": request.state.user})
