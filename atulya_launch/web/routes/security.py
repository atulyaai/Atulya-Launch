"""Routes for security audit."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_admin

router: APIRouter = APIRouter(prefix="/security")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_admin
async def security_page(request: Request) -> HTMLResponse:
    """Render the security audit page."""
    return templates.TemplateResponse(request, "security.html", {
        "user": request.state.user,
    })


@router.post("/audit")
@require_admin
async def run_audit(request: Request) -> JSONResponse:
    """Run a comprehensive security audit."""
    result: dict = core.comprehensive_security_audit()
    return JSONResponse(result)


@router.get("/api/audit")
@require_admin
async def api_audit(request: Request) -> JSONResponse:
    """API endpoint returning security audit results."""
    return JSONResponse(core.comprehensive_security_audit())
