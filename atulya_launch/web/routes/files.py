"""Routes for file browser and management."""
from fastapi import APIRouter, Request, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any

from ... import core
from ..auth import require_auth
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/files")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def files_root(request: Request) -> HTMLResponse:
    """Render the file manager root page."""
    sites: dict = core.site_list()
    return templates.TemplateResponse(request, "files.html", {
        "user": request.state.user,
        "domain": None,
        "sites": sites,
        "current_path": ".",
        "entries": [],
    })


@router.get("/{domain}", response_class=HTMLResponse)
@require_auth
async def file_browser(request: Request, domain: str, path: str = ".") -> HTMLResponse:
    """Browse files for a given domain."""
    try:
        entries: list[dict] = core.file_list(domain, path)
    except ValueError as e:
        return templates.TemplateResponse(request, "error.html", {"user": request.state.user, "error": str(e)}, status_code=404)
    return templates.TemplateResponse(request, "files.html", {
        "user": request.state.user,
        "domain": domain,
        "current_path": path,
        "entries": entries,
    })


@router.post("/{domain}/upload")
@require_auth
async def file_upload(request: Request, domain: str) -> Response:
    """Upload a file to a domain's web root."""
    form: Any = await request.form()
    upload: UploadFile | None = form.get("file")
    subpath: str = form.get("path", ".")
    if upload:
        filename: str = upload.filename
        content: bytes = await upload.read()
        try:
            core.file_write(domain, str(Path(subpath) / filename), content.decode("utf-8", errors="replace"))
            audit_log(request.state.user["username"], "file.upload", "ok", {"domain": domain, "file": filename})
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    return RedirectResponse(f"/files/{domain}?path={subpath}", status_code=302)


@router.post("/{domain}/mkdir")
@require_auth
async def file_mkdir(request: Request, domain: str, path: str = Form(...)) -> Response:
    """Create a directory in a domain's web root."""
    try:
        core.file_mkdir(domain, path)
        audit_log(request.state.user["username"], "file.mkdir", "ok", {"domain": domain, "path": path})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return RedirectResponse(f"/files/{domain}?path={str(Path(path).parent)}", status_code=302)


@router.post("/{domain}/delete")
@require_auth
async def file_delete(request: Request, domain: str, path: str = Form(...)) -> Response:
    """Delete a file or directory from a domain's web root."""
    try:
        core.file_delete(domain, path)
        audit_log(request.state.user["username"], "file.delete", "ok", {"domain": domain, "path": path})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return RedirectResponse(f"/files/{domain}?path={str(Path(path).parent)}", status_code=302)


@router.get("/api/{domain}/list")
@require_auth
async def api_file_list(request: Request, domain: str, path: str = ".") -> JSONResponse:
    """API endpoint listing files for a domain."""
    try:
        entries: list[dict] = core.file_list(domain, path)
        return JSONResponse(entries)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
