"""Routes for managing email accounts."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ..auth import require_auth
from ..database import audit_log
from .. import mail_service

router: APIRouter = APIRouter(prefix="/email")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def email_list(request: Request) -> HTMLResponse:
    """Render the email accounts list page."""
    accounts = mail_service.list_accounts()
    return templates.TemplateResponse(request, "email.html", {
        "user": request.state.user,
        "accounts": accounts,
    })


@router.post("/account/create")
@require_auth
async def account_create(request: Request, domain: str = Form(...), mailbox: str = Form(...), password: str = Form(...), quota_mb: int = Form(1024)) -> RedirectResponse:
    """Create a new email account."""
    result = mail_service.create_account(domain, mailbox, password, quota_mb)
    apply = result.get("apply", {})
    status = "ok" if apply.get("ok") else "error"
    audit_log(request.state.user["username"], "email.account_create", status, {"domain": domain, "mailbox": mailbox, "apply": apply})
    return RedirectResponse("/email", status_code=302)


@router.post("/account/delete")
@require_auth
async def account_delete(request: Request, account_id: int = Form(...)) -> RedirectResponse:
    """Delete an email account."""
    result = mail_service.delete_account(account_id)
    apply = result.get("apply", {})
    status = "ok" if apply.get("ok") else "error"
    audit_log(request.state.user["username"], "email.account_delete", status, {"account_id": account_id, "apply": apply})
    return RedirectResponse("/email", status_code=302)


@router.get("/api/accounts")
@require_auth
async def api_accounts(request: Request) -> JSONResponse:
    """API endpoint returning all email accounts."""
    return JSONResponse(mail_service.list_accounts())
