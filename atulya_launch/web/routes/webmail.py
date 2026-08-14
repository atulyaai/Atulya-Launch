from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth

router = APIRouter(prefix="/webmail", tags=["webmail"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def webmail_page(request: Request):
    status = core.webmail_status()
    return templates.TemplateResponse(request, "webmail.html", {
        "user": request.state.user,
        "status": status,
    })


@router.post("/install")
@require_auth
async def webmail_install(request: Request):
    core.webmail_install()
    return RedirectResponse("/webmail", status_code=302)


@router.get("/status")
@require_auth
async def webmail_status(request: Request):
    return JSONResponse(core.webmail_status())
