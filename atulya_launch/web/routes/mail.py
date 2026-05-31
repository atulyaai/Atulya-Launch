"""Routes for mail server setup and management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth, require_admin
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/mail", tags=["mail"])
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def mail_page(request: Request) -> HTMLResponse:
    """Render the mail management page."""
    domains: list[str] = list(core.site_list().keys())
    return templates.TemplateResponse(request, "mail.html", {
        "user": request.state.user,
        "domains": domains,
    })


@router.post("/setup")
@require_admin
async def mail_setup(request: Request, domain: str = Form(...)) -> JSONResponse:
    """Set up Postfix/Dovecot mail server for a domain."""
    result: dict = core.mail_setup(domain)
    status: str = "ok" if result.get("ok") else "error"
    audit_log(request.state.user["username"], "mail.setup", status, {"domain": domain})
    return JSONResponse(result)


@router.get("/status/{domain}")
@require_auth
async def mail_status(request: Request, domain: str) -> JSONResponse:
    """Get mail server status for a domain."""
    status: dict = core.mail_get_status(domain)
    return JSONResponse(status)


@router.post("/account/create")
@require_admin
async def mail_create_account(request: Request, domain: str = Form(...), mailbox: str = Form(...), password: str = Form(...)) -> JSONResponse:
    """Create a mail account for a domain."""
    result: dict = core.mail_create_account(domain, mailbox, password)
    status: str = "ok" if result.get("ok") else "error"
    audit_log(request.state.user["username"], "mail.account.create", status, {"domain": domain, "mailbox": mailbox})
    return JSONResponse(result)
