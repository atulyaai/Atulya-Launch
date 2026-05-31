"""Routes for managing email accounts."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any

from ..auth import require_auth, hash_password
from ..database import connect, audit_log

router: APIRouter = APIRouter(prefix="/email")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def email_list(request: Request) -> HTMLResponse:
    """Render the email accounts list page."""
    with connect() as cur:
        accounts: list[dict] = [dict(r) for r in cur.execute("SELECT id, domain, mailbox, quota_mb, created_at FROM email_accounts ORDER BY domain, mailbox").fetchall()]
    return templates.TemplateResponse(request, "email.html", {
        "user": request.state.user,
        "accounts": accounts,
    })


@router.post("/account/create")
@require_auth
async def account_create(request: Request, domain: str = Form(...), mailbox: str = Form(...), password: str = Form(...), quota_mb: int = Form(1024)) -> RedirectResponse:
    """Create a new email account."""
    pw_hash: str = hash_password(password)
    with connect() as cur:
        cur.execute(
            "INSERT INTO email_accounts (domain, mailbox, password_hash, quota_mb, created_at) VALUES (?, ?, ?, ?, ?)",
            (domain, mailbox, pw_hash, quota_mb, __import__("datetime").datetime.utcnow().isoformat() + "Z"),
        )
    audit_log(request.state.user["username"], "email.account_create", "ok", {"domain": domain, "mailbox": mailbox})
    return RedirectResponse("/email", status_code=302)


@router.post("/account/delete")
@require_auth
async def account_delete(request: Request, account_id: int = Form(...)) -> RedirectResponse:
    """Delete an email account."""
    with connect() as cur:
        cur.execute("DELETE FROM email_accounts WHERE id = ?", (account_id,))
    audit_log(request.state.user["username"], "email.account_delete", "ok", {"account_id": account_id})
    return RedirectResponse("/email", status_code=302)


@router.get("/api/accounts")
@require_auth
async def api_accounts(request: Request) -> JSONResponse:
    """API endpoint returning all email accounts."""
    with connect() as cur:
        accounts: list[dict] = [dict(r) for r in cur.execute("SELECT id, domain, mailbox, quota_mb, created_at FROM email_accounts").fetchall()]
    return JSONResponse(accounts)
