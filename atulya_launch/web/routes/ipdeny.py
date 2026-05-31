"""Routes for IP deny rule management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/ipdeny", tags=["ipdeny"])
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def ipdeny_page(request: Request) -> HTMLResponse:
    """Render the IP deny rules page."""
    domains: list[str] = list(core.site_list().keys())
    denied: dict = core.ip_deny_list()
    return templates.TemplateResponse(request, "ipdeny.html", {
        "user": request.state.user,
        "domains": domains,
        "denied": denied,
    })


@router.post("/add")
@require_auth
async def ipdeny_add(request: Request, domain: str = Form(...), ip_address: str = Form(...)) -> RedirectResponse:
    """Add an IP deny rule for a domain."""
    result: dict = core.ip_deny_add(domain, ip_address)
    audit_log(request.state.user["username"], "ipdeny.add", "ok" if result.get("ok") else "error",
              {"domain": domain, "ip": ip_address})
    return RedirectResponse("/ipdeny", status_code=302)


@router.post("/remove")
@require_auth
async def ipdeny_remove(request: Request, domain: str = Form(...), ip_address: str = Form(...)) -> RedirectResponse:
    """Remove an IP deny rule."""
    core.ip_deny_remove(domain, ip_address)
    return RedirectResponse("/ipdeny", status_code=302)
