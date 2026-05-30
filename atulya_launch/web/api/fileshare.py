"""Public file sharing link API."""

import json
import secrets
import shutil
import zipfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/files", tags=["files-share"])

SHARE_LINKS_FILE = utils.CONFIG_DIR / "file_shares.json"
ALLOWED_ROOTS = ["/var/www", "/home", "/tmp"]


def _safe_path(requested: str) -> Path:
    resolved = Path(requested).resolve()
    for root in ALLOWED_ROOTS:
        if str(resolved).startswith(root):
            return resolved
    raise HTTPException(status_code=403, detail="Access denied: path outside allowed roots")


def _load_shares() -> dict:
    if SHARE_LINKS_FILE.exists():
        with open(SHARE_LINKS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_shares(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SHARE_LINKS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _cleanup_expired():
    shares = _load_shares()
    import datetime
    now = datetime.datetime.now()
    expired = []
    for share_id, share in shares.items():
        expires_at = share.get("expires_at")
        if expires_at:
            try:
                exp = datetime.datetime.fromisoformat(expires_at)
                if now > exp:
                    expired.append(share_id)
            except (ValueError, TypeError):
                pass
    for share_id in expired:
        share_path = Path(shares[share_id].get("file_path", ""))
        if share_path.exists() and shares[share_id].get("temp_copy"):
            share_path.unlink(missing_ok=True)
        del shares[share_id]
    if expired:
        _save_shares(shares)


class ShareCreate(BaseModel):
    file_path: str
    password: Optional[str] = None
    expiry_hours: int = 24
    max_downloads: Optional[int] = None
    description: Optional[str] = None


@router.post("/share")
def create_share_link(body: ShareCreate, user: dict = Depends(get_current_user)):
    _cleanup_expired()

    source = _safe_path(body.file_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="File not found")

    share_id = secrets.token_urlsafe(16)
    import datetime
    expires_at = datetime.datetime.now() + datetime.timedelta(hours=body.expiry_hours)

    temp_copy = False
    if source.is_file():
        temp_dir = Path("/tmp/atulya_shares")
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / f"{share_id}_{source.name}"
        shutil.copy2(str(source), str(temp_path))
        file_path = str(temp_path)
        temp_copy = True
    else:
        file_path = str(source)

    share_data = {
        "id": share_id,
        "file_path": file_path,
        "original_path": str(source),
        "filename": source.name,
        "is_dir": source.is_dir(),
        "size": source.stat().st_size if source.exists() else 0,
        "password": body.password,
        "expires_at": expires_at.isoformat(),
        "max_downloads": body.max_downloads,
        "downloads": 0,
        "description": body.description,
        "temp_copy": temp_copy,
        "created_by": user.get("sub", "admin"),
        "created_at": datetime.datetime.now().isoformat(),
    }

    shares = _load_shares()
    shares[share_id] = share_data
    _save_shares(shares)

    return {"share": share_data, "url": f"/api/files/share/{share_id}/download"}


@router.get("/share/list")
def list_share_links(user: dict = Depends(get_current_user)):
    _cleanup_expired()
    shares = _load_shares()
    return {"shares": shares}


@router.delete("/share/{share_id}")
def revoke_share_link(share_id: str, user: dict = Depends(get_current_user)):
    shares = _load_shares()
    if share_id not in shares:
        raise HTTPException(status_code=404, detail="Share link not found")

    share = shares[share_id]
    if share.get("temp_copy"):
        share_path = Path(share.get("file_path", ""))
        if share_path.exists():
            share_path.unlink()

    del shares[share_id]
    _save_shares(shares)

    return {"status": "revoked", "id": share_id}


@router.get("/share/{share_id}/download")
def download_shared_file(share_id: str, password: Optional[str] = None):
    _cleanup_expired()
    shares = _load_shares()
    if share_id not in shares:
        raise HTTPException(status_code=404, detail="Share link not found or expired")

    share = shares[share_id]

    if share.get("expires_at"):
        import datetime
        try:
            expires = datetime.datetime.fromisoformat(share["expires_at"])
            if datetime.datetime.now() > expires:
                raise HTTPException(status_code=410, detail="Share link has expired")
        except (ValueError, TypeError):
            pass

    if share.get("password") and share["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid password")

    if share.get("max_downloads") and share["downloads"] >= share["max_downloads"]:
        raise HTTPException(status_code=410, detail="Download limit reached")

    file_path = Path(share.get("file_path", ""))
    if not file_path.exists():
        raise HTTPException(status_code=410, detail="Shared file no longer available")

    shares[share_id]["downloads"] = share.get("downloads", 0) + 1
    _save_shares(shares)

    if file_path.is_dir():
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in file_path.rglob("*"):
                if f.is_file():
                    zf.write(str(f), str(f.relative_to(file_path.parent)))
        zip_buffer.seek(0)
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            io.BytesIO(zip_buffer.read()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={share.get('filename', 'archive')}.zip"},
        )

    return FileResponse(str(file_path), filename=share.get("filename", file_path.name))
