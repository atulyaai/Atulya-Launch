"""File manager API."""

import os
import shutil
import stat
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/files", tags=["files"])

# Restrict file operations to allowed roots (security)
ALLOWED_ROOTS = ["/var/www", "/home"]


def _safe_path(requested: str) -> Path:
    """Resolve and validate a file path is within allowed roots."""
    resolved = Path(requested).resolve()
    for root in ALLOWED_ROOTS:
        if str(resolved).startswith(root):
            return resolved
    raise HTTPException(status_code=403, detail="Access denied: path outside allowed roots")


def _file_info(p: Path) -> dict:
    try:
        st = p.stat()
        return {
            "name": p.name,
            "path": str(p),
            "is_dir": p.is_dir(),
            "size": st.st_size if p.is_file() else 0,
            "permissions": oct(st.st_mode)[-3:],
            "modified": __import__("datetime").datetime.fromtimestamp(st.st_mtime).isoformat(),
        }
    except Exception as e:
        return {"name": p.name, "path": str(p), "error": str(e)}


class WriteBody(BaseModel):
    path: str
    content: str


class MkdirBody(BaseModel):
    path: str


class DeleteBody(BaseModel):
    path: str


class RenameBody(BaseModel):
    path: str
    new_name: str


class ChmodBody(BaseModel):
    path: str
    mode: str


@router.get("/list")
def list_directory(path: str = Query("/", description="Directory path"), user: dict = Depends(get_current_user)):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")
    entries = [_file_info(p) for p in sorted(target.iterdir())]
    return {"path": str(target), "files": entries}


@router.get("/read")
def read_file(path: str = Query(..., description="File path"), user: dict = Depends(get_current_user)):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"path": str(target), "content": content, "size": target.stat().st_size}


@router.post("/write")
def write_file(body: WriteBody, user: dict = Depends(get_current_user)):
    target = _safe_path(body.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    return {"status": "written", "path": str(target)}


@router.post("/mkdir")
def make_directory(body: MkdirBody, user: dict = Depends(get_current_user)):
    target = _safe_path(body.path)
    target.mkdir(parents=True, exist_ok=True)
    return {"status": "created", "path": str(target)}


@router.delete("/delete")
def delete_item(path: str = Query(..., description="Path to delete"), user: dict = Depends(get_current_user)):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"status": "deleted", "path": str(target)}


@router.post("/rename")
def rename_item(body: RenameBody, user: dict = Depends(get_current_user)):
    source = _safe_path(body.path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    dest = source.parent / body.new_name
    source.rename(dest)
    return {"status": "renamed", "from": str(source), "to": str(dest)}


@router.post("/chmod")
def change_permissions(body: ChmodBody, user: dict = Depends(get_current_user)):
    target = _safe_path(body.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    try:
        mode = int(body.mode, 8)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid permission mode")
    target.chmod(mode)
    return {"status": "permissions changed", "path": str(target), "mode": body.mode}


@router.post("/upload")
async def upload_file(path: str = Query("/", description="Target directory"), file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    target_dir = _safe_path(path)
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target is not a directory")
    dest = target_dir / file.filename
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)
    return {"status": "uploaded", "path": str(dest), "size": len(content)}


@router.get("/download")
def download_file(path: str = Query(..., description="File path"), user: dict = Depends(get_current_user)):
    target = _safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(target), filename=target.name)
