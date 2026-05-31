from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import connect, audit_log

router = APIRouter(prefix="/databases")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def databases_list(request: Request):
    with connect() as cur:
        databases = [dict(r) for r in cur.execute("SELECT id, name, db_type, username, created_at FROM databases ORDER BY name").fetchall()]
    return templates.TemplateResponse(request, "databases.html", {
        "user": request.state.user,
        "databases": databases,
    })


@router.post("/create")
@require_auth
async def db_create(request: Request, name: str = Form(...), db_type: str = Form("mysql"), username: str = Form(""), password: str = Form("")):
    pw_hash = hash_password(password) if password else None
    with connect() as cur:
        cur.execute(
            "INSERT INTO databases (name, db_type, username, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, db_type, username or None, pw_hash, __import__("datetime").datetime.utcnow().isoformat() + "Z"),
        )
    result = core.database_create(name, db_type)
    audit_log(request.state.user["username"], "database.create", "ok", {"name": name, "type": db_type})
    return RedirectResponse("/databases", status_code=302)


@router.post("/delete")
@require_auth
async def db_delete(request: Request, db_id: int = Form(...)):
    with connect() as cur:
        row = cur.execute("SELECT name, db_type FROM databases WHERE id = ?", (db_id,)).fetchone()
        if row:
            core.database_drop(row["name"], row["db_type"])
            cur.execute("DELETE FROM databases WHERE id = ?", (db_id,))
    audit_log(request.state.user["username"], "database.delete", "ok", {"db_id": db_id})
    return RedirectResponse("/databases", status_code=302)


@router.post("/{db_id}/backup")
@require_auth
async def db_backup(request: Request, db_id: int):
    with connect() as cur:
        row = cur.execute("SELECT name, db_type FROM databases WHERE id = ?", (db_id,)).fetchone()
    if row:
        result = core.database_backup(row["name"], row["db_type"])
        audit_log(request.state.user["username"], "database.backup", "ok", {"name": row["name"]})
        return JSONResponse(result)
    return JSONResponse({"error": "database not found"}, status_code=404)


@router.get("/api/databases")
@require_auth
async def api_databases(request: Request):
    with connect() as cur:
        databases = [dict(r) for r in cur.execute("SELECT id, name, db_type, username, created_at FROM databases").fetchall()]
    return JSONResponse(databases)
