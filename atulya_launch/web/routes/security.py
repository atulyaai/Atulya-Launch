from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth, require_admin
from ..database import connect

router = APIRouter(prefix="/security")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_admin
async def security_page(request: Request):
    return templates.TemplateResponse(request, "security.html", {
        "user": request.state.user,
    })


@router.post("/audit")
@require_admin
async def run_audit(request: Request):
    result = core.comprehensive_security_audit()
    return JSONResponse(result)


@router.get("/api/audit")
@require_admin
async def api_audit(request: Request):
    return JSONResponse(core.comprehensive_security_audit())
