"""Routes for subdomain and parked domain management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/subdomains", tags=["subdomains"])
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def subdomain_page(request: Request) -> HTMLResponse:
    """Render the subdomains and parked domains page."""
    domains: list[str] = list(core.site_list().keys())
    subs: dict = core.subdomain_list()
    parked: dict = core.parked_domain_list()
    return templates.TemplateResponse(request, "subdomains.html", {
        "user": request.state.user,
        "domains": domains,
        "subdomains": subs,
        "parked": parked,
    })


@router.post("/create")
@require_auth
async def subdomain_create(request: Request, domain: str = Form(...), subdomain: str = Form(...), target: str = Form("")) -> RedirectResponse:
    """Create a new subdomain."""
    result: dict = core.subdomain_create(domain, subdomain, target or None)
    audit_log(request.state.user["username"], "subdomain.create", "ok" if result.get("ok") else "error",
              {"domain": domain, "subdomain": subdomain})
    return RedirectResponse("/subdomains", status_code=302)


@router.post("/delete")
@require_auth
async def subdomain_delete(request: Request, domain: str = Form(...), subdomain: str = Form(...)) -> RedirectResponse:
    """Delete a subdomain."""
    core.subdomain_delete(domain, subdomain)
    return RedirectResponse("/subdomains", status_code=302)


@router.post("/park/create")
@require_auth
async def park_create(request: Request, primary_domain: str = Form(...), parked_domain: str = Form(...)) -> RedirectResponse:
    """Park a domain on an existing primary domain."""
    result: dict = core.parked_domain_create(primary_domain, parked_domain)
    audit_log(request.state.user["username"], "parked.create", "ok" if result.get("ok") else "error",
              {"primary": primary_domain, "parked": parked_domain})
    return RedirectResponse("/subdomains", status_code=302)


@router.post("/park/delete")
@require_auth
async def park_delete(request: Request, parked_domain: str = Form(...)) -> RedirectResponse:
    """Remove a parked domain."""
    core.parked_domain_delete(parked_domain)
    return RedirectResponse("/subdomains", status_code=302)
