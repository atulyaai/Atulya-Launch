"""Routes for URL redirect management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/redirects", tags=["redirects"])
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def redirect_page(request: Request) -> HTMLResponse:
    """Render the redirects management page."""
    domains: list[str] = list(core.site_list().keys())
    redirects: dict = core.redirect_list()
    return templates.TemplateResponse(request, "redirects.html", {
        "user": request.state.user,
        "domains": domains,
        "redirects": redirects,
    })


@router.post("/create")
@require_auth
async def redirect_create(request: Request, domain: str = Form(...), source_path: str = Form(...), target_url: str = Form(...), redirect_type: int = Form(301)) -> RedirectResponse:
    """Create a URL redirect rule."""
    result: dict = core.redirect_create(domain, source_path, target_url, redirect_type)
    audit_log(request.state.user["username"], "redirect.create", "ok" if result.get("ok") else "error",
              {"domain": domain, "source": source_path, "target": target_url})
    return RedirectResponse("/redirects", status_code=302)


@router.post("/delete")
@require_auth
async def redirect_delete(request: Request, domain: str = Form(...), source_path: str = Form(...)) -> RedirectResponse:
    """Delete a URL redirect rule."""
    core.redirect_delete(domain, source_path)
    return RedirectResponse("/redirects", status_code=302)
