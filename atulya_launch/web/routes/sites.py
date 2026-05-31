"""Routes for managing sites."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any

from ... import core
from ..auth import require_auth
from ..database import audit_log
from .. import sites_service

router: APIRouter = APIRouter(prefix="/sites")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def sites_list(request: Request) -> HTMLResponse:
    """Render the sites list page."""
    sites: dict = sites_service.list_sites()
    return templates.TemplateResponse(request, "sites.html", {
        "user": request.state.user,
        "sites": sites,
    })


@router.post("/create")
@require_auth
async def sites_create(request: Request, domain: str = Form(...), proxy_pass: str = Form(""), php: bool = Form(False), php_version: str = Form("8.3")) -> RedirectResponse:
    """Create a new site domain."""
    try:
        sites_service.create_site(domain, proxy_pass=proxy_pass or None, php=php, php_version=php_version if php else None)
        audit_log(request.state.user["username"], "site.create", "ok", {"domain": domain})
    except ValueError as e:
        audit_log(request.state.user["username"], "site.create", "error", {"domain": domain, "error": str(e)})
    return RedirectResponse("/sites", status_code=302)


@router.post("/php-version")
@require_auth
async def sites_php_version(request: Request, domain: str = Form(...), php_version: str = Form(...)) -> RedirectResponse:
    """Change the PHP version for a site."""
    try:
        sites_service.set_php_version(domain, php_version)
        audit_log(request.state.user["username"], "site.php_version", "ok", {"domain": domain, "version": php_version})
    except ValueError as e:
        audit_log(request.state.user["username"], "site.php_version", "error", {"domain": domain, "error": str(e)})
    return RedirectResponse("/sites", status_code=302)


@router.post("/delete")
@require_auth
async def sites_delete(request: Request, domain: str = Form(...)) -> RedirectResponse:
    """Delete a site."""
    sites_service.delete_site(domain)
    audit_log(request.state.user["username"], "site.delete", "ok", {"domain": domain})
    return RedirectResponse("/sites", status_code=302)


@router.post("/{domain}/enable")
@require_auth
async def sites_enable(request: Request, domain: str) -> JSONResponse:
    """Enable a site."""
    try:
        result = sites_service.toggle_site(domain, True)
        return JSONResponse({"status": "enabled", "domain": domain})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/{domain}/disable")
@require_auth
async def sites_disable(request: Request, domain: str) -> JSONResponse:
    """Disable a site."""
    try:
        result = sites_service.toggle_site(domain, False)
        return JSONResponse({"status": "disabled", "domain": domain})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/{domain}/nginx/reload")
@require_auth
async def nginx_reload(request: Request, domain: str) -> JSONResponse:
    """Apply nginx config and reload for a domain."""
    result: dict = core.nginx_apply_and_reload(domain)
    audit_log(request.state.user["username"], "nginx.reload", "ok" if result.get("ok") else "error", {"domain": domain})
    return JSONResponse(result)


@router.get("/api/list")
@require_auth
async def api_sites(request: Request) -> JSONResponse:
    """API endpoint returning all sites."""
    return JSONResponse(list(sites_service.list_sites().values()))
