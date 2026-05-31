"""File compression and decompression API."""

import json
import shutil
import zipfile
import tarfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/files", tags=["files-compress"])

ALLOWED_ROOTS = ["/var/www", "/home", "/tmp"]


def _safe_path(requested: str) -> Path:
    resolved = Path(requested).resolve()
    for root in ALLOWED_ROOTS:
        if str(resolved).startswith(root):
            return resolved
    raise HTTPException(status_code=403, detail="Access denied: path outside allowed roots")


class CompressRequest(BaseModel):
    sources: list
    output_path: str
    archive_type: str = "zip"
    compression_level: int = 6


class DecompressRequest(BaseModel):
    source: str
    output_dir: Optional[str] = None


@router.post("/compress")
def compress_files(body: CompressRequest, user: dict = Depends(get_current_user)):
    output = _safe_path(body.output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if body.archive_type == "zip":
        if not body.output_path.endswith(".zip"):
            raise HTTPException(status_code=400, detail="Output path must end with .zip")

        try:
            with zipfile.ZipFile(str(output), "w", zipfile.ZIP_DEFLATED if body.compression_level > 0 else zipfile.ZIP_STORED) as zf:
                for src in body.sources:
                    source = _safe_path(src)
                    if source.is_file():
                        zf.write(str(source), source.name)
                    elif source.is_dir():
                        for file_path in source.rglob("*"):
                            if file_path.is_file():
                                arcname = str(file_path.relative_to(source.parent))
                                zf.write(str(file_path), arcname)
                    else:
                        raise HTTPException(status_code=404, detail=f"Source not found: {src}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Compression failed: {e}")

    elif body.archive_type in ("tar", "tar.gz", "tgz"):
        mode = "w:gz" if body.archive_type in ("tar.gz", "tgz") else "w"
        try:
            with tarfile.open(str(output), mode) as tf:
                for src in body.sources:
                    source = _safe_path(src)
                    if source.exists():
                        tf.add(str(source), arcname=source.name)
                    else:
                        raise HTTPException(status_code=404, detail=f"Source not found: {src}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Compression failed: {e}")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported archive type: {body.archive_type}")

    return {
        "status": "compressed",
        "output": str(output),
        "size": output.stat().st_size,
        "archive_type": body.archive_type,
    }


@router.post("/decompress")
def decompress_files(body: DecompressRequest, user: dict = Depends(get_current_user)):
    source = _safe_path(body.source)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Archive not found")

    output_dir = _safe_path(body.output_dir) if body.output_dir else source.parent / source.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    if source.suffix == ".zip":
        try:
            with zipfile.ZipFile(str(source), "r") as zf:
                zf.extractall(str(output_dir))
        except zipfile.BadZipFile as e:
            raise HTTPException(status_code=400, detail=f"Invalid zip file: {e}")
    elif source.suffix in (".gz", ".tgz") or source.name.endswith(".tar.gz"):
        try:
            with tarfile.open(str(source), "r:gz") as tf:
                tf.extractall(str(output_dir))
        except tarfile.TarError as e:
            raise HTTPException(status_code=400, detail=f"Invalid tar archive: {e}")
    elif source.suffix == ".tar":
        try:
            with tarfile.open(str(source), "r") as tf:
                tf.extractall(str(output_dir))
        except tarfile.TarError as e:
            raise HTTPException(status_code=400, detail=f"Invalid tar archive: {e}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported archive format")

    return {
        "status": "decompressed",
        "source": str(source),
        "output_dir": str(output_dir),
    }
