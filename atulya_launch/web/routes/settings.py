from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth, require_admin, hash_password
from ..database import connect, audit_log

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def settings_page(request: Request):
    with connect() as cur:
        users = [dict(r) for r in cur.execute("SELECT id, username, role, created_at, last_login FROM users ORDER BY username").fetchall()]
    cfg = core.load_config()
    return templates.TemplateResponse(request, "settings.html", {
        "user": request.state.user,
        "users": users,
        "panel_config": cfg.get("panel", {}),
        "settings": cfg.get("settings", {}),
    })


@router.post("/password")
@require_auth
async def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...)):
    user = request.state.user
    from ..auth import verify_password
    with connect() as cur:
        row = cur.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            return RedirectResponse("/settings?error=bad_password", status_code=302)
        cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user["id"]))
    audit_log(user["username"], "settings.password_change", "ok")
    return RedirectResponse("/settings?success=1", status_code=302)


@router.post("/user/create")
@require_admin
async def user_create(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("user")):
    from ..auth import create_user
    try:
        create_user(username, password, role)
        audit_log(request.state.user["username"], "settings.user_create", "ok", {"new_user": username, "role": role})
    except Exception as e:
        audit_log(request.state.user["username"], "settings.user_create", "error", {"error": str(e)})
    return RedirectResponse("/settings", status_code=302)


@router.post("/user/delete")
@require_admin
async def user_delete(request: Request, user_id: int = Form(...)):
    if request.state.user["id"] == user_id:
        return RedirectResponse("/settings?error=.self_delete", status_code=302)
    with connect() as cur:
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    audit_log(request.state.user["username"], "settings.user_delete", "ok", {"user_id": user_id})
    return RedirectResponse("/settings", status_code=302)


@router.get("/api/config")
@require_auth
async def api_config(request: Request):
    cfg = core.load_config()
    safe = {k: v for k, v in cfg.items() if k not in ("sessions",)}
    return JSONResponse(safe)
