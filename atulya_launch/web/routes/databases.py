"""Routes for managing databases."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any

from ... import core
from ..auth import require_auth, hash_password
from ..database import connect, audit_log

router: APIRouter = APIRouter(prefix="/databases")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def databases_list(request: Request) -> HTMLResponse:
    """Render the databases management page."""
    with connect() as cur:
        databases: list[dict] = [dict(r) for r in cur.execute("SELECT id, name, db_type, username, created_at FROM databases ORDER BY name").fetchall()]
    pma: dict = core.phpmyadmin_status()
    return templates.TemplateResponse(request, "databases.html", {
        "user": request.state.user,
        "databases": databases,
        "phpmyadmin_installed": pma.get("installed", False),
    })


@router.post("/create")
@require_auth
async def db_create(request: Request, name: str = Form(...), db_type: str = Form("mysql"), username: str = Form(""), password: str = Form("")) -> RedirectResponse:
    """Create a new database."""
    pw_hash: str | None = hash_password(password) if password else None
    with connect() as cur:
        cur.execute(
            "INSERT INTO databases (name, db_type, username, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, db_type, username or None, pw_hash, __import__("datetime").datetime.utcnow().isoformat() + "Z"),
        )
    core.database_create(name, db_type)
    audit_log(request.state.user["username"], "database.create", "ok", {"name": name, "type": db_type})
    return RedirectResponse("/databases", status_code=302)


@router.post("/delete")
@require_auth
async def db_delete(request: Request, db_id: int = Form(...)) -> RedirectResponse:
    """Delete a database."""
    with connect() as cur:
        row: Any = cur.execute("SELECT name, db_type FROM databases WHERE id = ?", (db_id,)).fetchone()
        if row:
            core.database_drop(row["name"], row["db_type"])
            cur.execute("DELETE FROM databases WHERE id = ?", (db_id,))
    audit_log(request.state.user["username"], "database.delete", "ok", {"db_id": db_id})
    return RedirectResponse("/databases", status_code=302)


@router.post("/{db_id}/backup")
@require_auth
async def db_backup(request: Request, db_id: int) -> JSONResponse:
    """Backup a database."""
    with connect() as cur:
        row: Any = cur.execute("SELECT name, db_type FROM databases WHERE id = ?", (db_id,)).fetchone()
    if row:
        result: dict = core.database_backup(row["name"], row["db_type"])
        audit_log(request.state.user["username"], "database.backup", "ok", {"name": row["name"]})
        return JSONResponse(result)
    return JSONResponse({"error": "database not found"}, status_code=404)


@router.get("/api/databases")
@require_auth
async def api_databases(request: Request) -> JSONResponse:
    """API endpoint returning all databases."""
    with connect() as cur:
        databases: list[dict] = [dict(r) for r in cur.execute("SELECT id, name, db_type, username, created_at FROM databases").fetchall()]
    return JSONResponse(databases)


@router.post("/phpmyadmin/install")
@require_auth
async def phpmyadmin_install(request: Request) -> RedirectResponse:
    """Install phpMyAdmin."""
    result: dict = core.phpmyadmin_install()
    audit_log(request.state.user["username"], "phpmyadmin.install", "ok" if result.get("ok") else "error")
    return RedirectResponse("/databases", status_code=302)


@router.get("/phpmyadmin/status")
@require_auth
async def phpmyadmin_status(request: Request) -> JSONResponse:
    """Check phpMyAdmin installation status."""
    return JSONResponse(core.phpmyadmin_status())
