"""Routes for importing and managing migrations from other control panels."""
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import tempfile

from ... import core
from ..auth import require_auth, require_admin
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/migrations")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_admin
async def migrations_page(request: Request) -> HTMLResponse:
    """Render the migration import page."""
    return templates.TemplateResponse(request, "migrations.html", {
        "user": request.state.user,
        "sources": core.MIGRATION_SOURCES,
        "migrations": core.migration_list(),
    })


@router.post("/import")
@require_admin
async def migration_import(request: Request, source: str = Form(...), file: UploadFile = File(...), domain: str = Form("")) -> RedirectResponse:
    """Import a migration archive from a source panel."""
    suffix: str = Path(file.filename).suffix if file.filename else ".tar.gz"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content: bytes = await file.read()
        tmp.write(content)
        tmp_path: str = tmp.name
    try:
        result: dict = core.migration_import(source, tmp_path, domain=domain or None)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if not result.get("ok"):
        audit_log(request.state.user["username"], "migration.import", "error", {"source": source, "error": result.get("error")})
        return RedirectResponse("/migrations?error=import_failed", status_code=302)
    audit_log(request.state.user["username"], "migration.import", "ok", {"source": source, **result})
    return RedirectResponse("/migrations?success=1", status_code=302)


@router.post("/delete")
@require_admin
async def migration_delete(request: Request, migration_id: int = Form(...)) -> RedirectResponse:
    """Delete a migration record."""
    core.migration_delete(migration_id)
    return RedirectResponse("/migrations", status_code=302)


@router.get("/api/sources")
@require_auth
async def api_sources(request: Request) -> JSONResponse:
    """API endpoint returning available migration sources."""
    return JSONResponse(core.MIGRATION_SOURCES)
