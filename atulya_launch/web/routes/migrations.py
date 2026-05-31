from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import tempfile, shutil

from ... import core
from ..auth import require_auth, require_admin
from ..database import audit_log

router = APIRouter(prefix="/migrations")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_admin
async def migrations_page(request: Request):
    return templates.TemplateResponse(request, "migrations.html", {
        "user": request.state.user,
        "sources": core.MIGRATION_SOURCES,
        "migrations": core.migration_list(),
    })


@router.post("/import")
@require_admin
async def migration_import(request: Request, source: str = Form(...), file: UploadFile = File(...), domain: str = Form("")):
    suffix = Path(file.filename).suffix if file.filename else ".tar.gz"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = core.migration_import(source, tmp_path, domain=domain or None)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if not result.get("ok"):
        audit_log(request.state.user["username"], "migration.import", "error", {"source": source, "error": result.get("error")})
        return RedirectResponse("/migrations?error=import_failed", status_code=302)
    audit_log(request.state.user["username"], "migration.import", "ok", {"source": source, **result})
    return RedirectResponse("/migrations?success=1", status_code=302)


@router.post("/delete")
@require_admin
async def migration_delete(request: Request, migration_id: int = Form(...)):
    core.migration_delete(migration_id)
    return RedirectResponse("/migrations", status_code=302)


@router.get("/api/sources")
@require_auth
async def api_sources(request: Request):
    return JSONResponse(core.MIGRATION_SOURCES)
