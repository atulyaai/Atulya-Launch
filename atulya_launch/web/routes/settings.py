"""Routes for panel settings, user management, plans, branding, tokens, and 2FA."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any

from ... import core
from ..auth import require_auth, require_admin, require_reseller, hash_password, verify_password, create_user
from ..database import connect, audit_log

router: APIRouter = APIRouter(prefix="/settings")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def settings_page(request: Request) -> HTMLResponse:
    """Render the settings page with users, config, plans, branding, and tokens."""
    with connect() as cur:
        users: list[dict] = [dict(r) for r in cur.execute("SELECT id, username, role, created_at, last_login FROM users ORDER BY username").fetchall()]
    cfg: dict = core.load_config()
    plans: list[dict] = core.plan_list()
    branding: dict = core.branding_get_all()
    resellers: list[dict] = core.reseller_list() if request.state.user.get("role") == "admin" else []
    my_clients: list[dict] = core.reseller_list_clients(request.state.user["id"]) if request.state.user.get("role") == "reseller" else []
    api_tokens: list[dict] = core.api_token_list()
    twofa: dict = core.twofa_status(request.state.user["username"])
    return templates.TemplateResponse(request, "settings.html", {
        "user": request.state.user,
        "users": users,
        "panel_config": cfg.get("panel", {}),
        "settings": cfg.get("settings", {}),
        "plans": plans,
        "branding": branding,
        "resellers": resellers,
        "my_clients": my_clients,
        "api_tokens": api_tokens,
        "twofa_enabled": twofa.get("enabled", False),
    })


@router.post("/password")
@require_auth
async def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...)) -> RedirectResponse:
    """Change the current user's password."""
    user: Any = request.state.user
    with connect() as cur:
        row: Any = cur.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            return RedirectResponse("/settings?error=bad_password", status_code=302)
        cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user["id"]))
    audit_log(user["username"], "settings.password_change", "ok")
    return RedirectResponse("/settings?success=1", status_code=302)


@router.post("/user/create")
@require_admin
async def user_create_handler(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("user")) -> RedirectResponse:
    """Create a new user (admin only)."""
    try:
        create_user(username, password, role)
        audit_log(request.state.user["username"], "settings.user_create", "ok", {"new_user": username, "role": role})
    except Exception as e:
        audit_log(request.state.user["username"], "settings.user_create", "error", {"error": str(e)})
    return RedirectResponse("/settings", status_code=302)


@router.post("/user/delete")
@require_admin
async def user_delete_handler(request: Request, user_id: int = Form(...)) -> RedirectResponse:
    """Delete a user (admin only, cannot delete self)."""
    if request.state.user["id"] == user_id:
        return RedirectResponse("/settings?error=.self_delete", status_code=302)
    with connect() as cur:
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    audit_log(request.state.user["username"], "settings.user_delete", "ok", {"user_id": user_id})
    return RedirectResponse("/settings", status_code=302)


@router.post("/plan/create")
@require_auth
async def plan_create_handler(request: Request, name: str = Form(...), sites_limit: int = Form(0), disk_limit_mb: int = Form(0), db_limit: int = Form(0), email_limit: int = Form(0), bandwidth_limit_mb: int = Form(0), price_monthly: float = Form(0)) -> RedirectResponse:
    """Create a new hosting plan."""
    if request.state.user.get("role") not in ("admin", "reseller"):
        return RedirectResponse("/dashboard", status_code=302)
    core.plan_create(name, sites_limit, disk_limit_mb, db_limit, email_limit, bandwidth_limit_mb, price_monthly)
    return RedirectResponse("/settings", status_code=302)


@router.post("/plan/delete")
@require_admin
async def plan_delete_handler(request: Request, plan_id: int = Form(...)) -> RedirectResponse:
    """Delete a hosting plan."""
    core.plan_delete(plan_id)
    return RedirectResponse("/settings", status_code=302)


@router.post("/plan/assign")
@require_admin
async def plan_assign_handler(request: Request, user_id: int = Form(...), plan_id: int = Form(...)) -> RedirectResponse:
    """Assign a plan to a user."""
    core.plan_assign(user_id, plan_id)
    return RedirectResponse("/settings", status_code=302)


@router.post("/branding/set")
@require_admin
async def branding_set_handler(request: Request, key: str = Form(...), value: str = Form("")) -> RedirectResponse:
    """Set a branding key-value pair."""
    core.branding_set(key, value)
    return RedirectResponse("/settings", status_code=302)


@router.post("/branding/delete")
@require_admin
async def branding_delete_handler(request: Request, key: str = Form(...)) -> RedirectResponse:
    """Delete a branding key."""
    core.branding_delete(key)
    return RedirectResponse("/settings", status_code=302)


@router.get("/api/config")
@require_auth
async def api_config(request: Request) -> JSONResponse:
    """API endpoint returning panel config (excluding sessions)."""
    cfg: dict = core.load_config()
    safe: dict = {k: v for k, v in cfg.items() if k not in ("sessions",)}
    return JSONResponse(safe)


@router.post("/reseller/create")
@require_admin
async def reseller_create_handler(request: Request, username: str = Form(...), password: str = Form(...), max_clients: int = Form(5), max_sites: int = Form(10), max_dbs: int = Form(5), max_emails: int = Form(10), disk_limit_mb: int = Form(1024)) -> RedirectResponse:
    """Create a reseller account with allocation limits."""
    result: dict = core.reseller_create(username, password, max_clients, max_sites, max_dbs, max_emails, disk_limit_mb)
    audit_log(request.state.user["username"], "settings.reseller_create", "ok" if result.get("ok") else "error", {"username": username})
    return RedirectResponse("/settings", status_code=302)


@router.post("/reseller/delete")
@require_admin
async def reseller_delete_handler(request: Request, user_id: int = Form(...)) -> RedirectResponse:
    """Delete a reseller user."""
    with connect() as cur:
        cur.execute("DELETE FROM users WHERE id = ? AND role = 'reseller'", (user_id,))
    return RedirectResponse("/settings", status_code=302)


@router.post("/client/create")
@require_reseller
async def client_create_handler(request: Request, username: str = Form(...), password: str = Form(...), plan_id: int = Form(0)) -> RedirectResponse:
    """Create a client under the current reseller."""
    result: dict = core.reseller_create_client(request.state.user["id"], username, password, plan_id if plan_id > 0 else None)
    audit_log(request.state.user["username"], "settings.client_create", "ok" if result.get("ok") else "error", {"username": username})
    return RedirectResponse("/settings", status_code=302)


@router.post("/client/delete")
@require_reseller
async def client_delete_handler(request: Request, client_id: int = Form(...)) -> RedirectResponse:
    """Delete a client under the current reseller."""
    core.reseller_delete_client(client_id)
    return RedirectResponse("/settings", status_code=302)


@router.post("/token/create")
@require_auth
async def token_create_handler(request: Request, name: str = Form(...), permissions: str = Form([]), expires_days: int = Form(365)) -> RedirectResponse:
    """Create a new API token."""
    perms: list[str] = [p.strip() for p in permissions.split(",") if p.strip()] if isinstance(permissions, str) else permissions
    core.api_token_create(name, perms or ["read"], expires_days)
    return RedirectResponse("/settings", status_code=302)


@router.post("/token/delete")
@require_auth
async def token_delete_handler(request: Request, token_id: str = Form(...)) -> RedirectResponse:
    """Delete an API token."""
    core.api_token_delete(token_id)
    return RedirectResponse("/settings", status_code=302)


@router.post("/api/2fa/generate")
@require_auth
async def twofa_generate(request: Request) -> JSONResponse:
    """Generate a 2FA secret for the current user."""
    user: Any = request.state.user
    result: dict = core.twofa_generate_secret(user["username"])
    return JSONResponse(result)


@router.post("/api/2fa/enable")
@require_auth
async def twofa_enable(request: Request, body: dict) -> JSONResponse:
    """Enable 2FA with a verification code."""
    user: Any = request.state.user
    code: str = body.get("code", "")
    result: dict = core.twofa_enable(user["username"], code)
    return JSONResponse(result)


@router.post("/2fa/disable")
@require_auth
async def twofa_disable(request: Request, code: str = Form(...)) -> RedirectResponse:
    """Disable 2FA with a verification code."""
    user: Any = request.state.user
    result: dict = core.twofa_disable(user["username"], code)
    return RedirectResponse("/settings?2fa=" + ("disabled" if result.get("ok") else "failed"), status_code=302)
