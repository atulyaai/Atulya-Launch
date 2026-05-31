"""Antivirus Scanner - ClamAV integration for file uploads."""

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/antivirus", tags=["antivirus"])

AV_DIR = utils.CONFIG_DIR / "antivirus"
CONFIG_FILE = AV_DIR / "config.json"
QUARANTINE_DIR = AV_DIR / "quarantine"
SCAN_LOG = AV_DIR / "scan.log"


def _ensure_dirs():
    AV_DIR.mkdir(parents=True, exist_ok=True)
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({
            "enabled": False,
            "scan_uploads": True,
            "scan_on_demand": True,
            "quarantine_infected": True,
            "alert_on_detection": True,
            "last_scan": None,
            "total_scans": 0,
            "total_viruses_found": 0,
        }, indent=2))


def _load_config() -> dict:
    _ensure_dirs()
    return json.loads(CONFIG_FILE.read_text())


def _save_config(data: dict):
    _ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


class AVConfig(BaseModel):
    enabled: Optional[bool] = None
    scan_uploads: Optional[bool] = None
    quarantine_infected: Optional[bool] = None


def _is_clamav_installed() -> bool:
    if not utils.is_linux():
        return False
    result = utils.run_command(["which", "clamscan"], check=False)
    return result and hasattr(result, 'returncode') and result.returncode == 0


def _scan_file(file_path: str) -> dict:
    if not _is_clamav_installed():
        return {"clean": True, "message": "ClamAV not installed", "engine": "none"}

    result = utils.run_command(
        ["clamscan", "--no-summary", "--infected", str(file_path)],
        check=False,
    )

    output = ""
    if result and hasattr(result, 'stdout'):
        output = result.stdout or ""
    if result and hasattr(result, 'stderr'):
        output += result.stderr or ""

    infected = result and hasattr(result, 'returncode') and result.returncode == 1

    if infected:
        virus_name = "unknown"
        for line in output.split('\n'):
            if "FOUND" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    virus_name = parts[-1].strip().replace(" FOUND", "")
                    break

        return {"clean": False, "virus": virus_name, "engine": "clamav"}

    return {"clean": True, "engine": "clamav"}


def _scan_bytes(data: bytes) -> dict:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        return _scan_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/status")
def antivirus_status(user: dict = Depends(get_current_user)):
    config = _load_config()
    clamav_installed = _is_clamav_installed()
    db_version = None

    if clamav_installed and utils.is_linux():
        result = utils.run_command(["sigtool", "--info", "/var/lib/clamav/main.cvd"], check=False)
        if result and hasattr(result, 'stdout'):
            for line in (result.stdout or "").split('\n'):
                if 'Version:' in line:
                    db_version = line.split(':')[-1].strip()

    return {
        "enabled": config.get("enabled", False),
        "engine": "clamav" if clamav_installed else "none",
        "installed": clamav_installed,
        "db_version": db_version,
        "scan_uploads": config.get("scan_uploads", True),
        "quarantine_dir": str(QUARANTINE_DIR),
        "stats": {
            "total_scans": config.get("total_scans", 0),
            "total_viruses": config.get("total_viruses_found", 0),
            "last_scan": config.get("last_scan"),
        },
    }


@router.get("/config")
def get_config(user: dict = Depends(get_current_user)):
    return _load_config()


@router.post("/config")
def update_config(body: AVConfig, user: dict = Depends(get_current_user)):
    config = _load_config()
    if body.enabled is not None:
        if body.enabled and not _is_clamav_installed():
            if utils.is_linux():
                utils.run_command(["apt-get", "install", "-y", "clamav", "clamav-daemon"], check=False)
                utils.run_command(["freshclam"], check=False)
            else:
                raise HTTPException(status_code=400, detail="ClamAV installation requires Linux")
        config["enabled"] = body.enabled
    if body.scan_uploads is not None:
        config["scan_uploads"] = body.scan_uploads
    if body.quarantine_infected is not None:
        config["quarantine_infected"] = body.quarantine_infected
    _save_config(config)
    return {"status": "updated", "config": config}


@router.post("/scan/file")
def scan_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    config = _load_config()
    if not config.get("enabled"):
        return {"clean": True, "message": "Antivirus scanning is disabled"}

    content = file.file.read()
    result = _scan_bytes(content)

    config["total_scans"] = config.get("total_scans", 0) + 1
    if not result.get("clean"):
        config["total_viruses_found"] = config.get("total_viruses_found", 0) + 1

        if config.get("quarantine_infected"):
            quarantine_file = QUARANTINE_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            quarantine_file.write_bytes(content)
    config["last_scan"] = datetime.now().isoformat()
    _save_config(config)

    return result


@router.post("/scan/path")
def scan_path(body: dict, user: dict = Depends(get_current_user)):
    config = _load_config()
    if not config.get("enabled"):
        return {"clean": True, "message": "Antivirus scanning is disabled"}

    path = body.get("path", "")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=400, detail="Invalid path")

    result = _scan_file(path)

    config["total_scans"] = config.get("total_scans", 0) + 1
    if not result.get("clean"):
        config["total_viruses_found"] = config.get("total_viruses_found", 0) + 1
    config["last_scan"] = datetime.now().isoformat()
    _save_config(config)

    return result


@router.post("/scan/directory")
def scan_directory(body: dict, user: dict = Depends(get_current_user)):
    config = _load_config()
    if not config.get("enabled"):
        return {"clean": True, "message": "Antivirus scanning is disabled"}

    path = body.get("path", "/var/www")
    if not Path(path).exists():
        raise HTTPException(status_code=400, detail="Invalid path")

    if not _is_clamav_installed():
        return {"clean": True, "message": "ClamAV not installed", "engine": "none"}

    result = utils.run_command(
        ["clamscan", "-r", "--infected", "--log", str(AV_DIR / "last_recursive_scan.log"), str(path)],
        check=False,
        timeout=300,
    )

    infected_files = []
    scan_log = AV_DIR / "last_recursive_scan.log"
    if scan_log.exists():
        for line in scan_log.read_text().split('\n'):
            if "FOUND" in line:
                infected_files.append(line.strip())

    config["total_scans"] = config.get("total_scans", 1) + 1
    config["last_scan"] = datetime.now().isoformat()
    if infected_files:
        config["total_viruses_found"] = config.get("total_viruses_found", 0) + len(infected_files)
    _save_config(config)

    return {
        "clean": len(infected_files) == 0,
        "infected_files": infected_files,
        "scanned_path": path,
        "engine": "clamav",
    }


@router.get("/quarantine")
def list_quarantine(user: dict = Depends(get_current_user)):
    files = []
    if QUARANTINE_DIR.exists():
        for f in QUARANTINE_DIR.iterdir():
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "quarantined_at": datetime.fromtimestamp(f.stat().st_ctime).isoformat(),
                })
    return {"quarantine": files, "count": len(files)}


@router.delete("/quarantine/{filename}")
def delete_quarantine(filename: str, user: dict = Depends(get_current_user)):
    target = QUARANTINE_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found in quarantine")
    target.unlink()
    return {"status": "deleted", "filename": filename}


@router.post("/update-database")
def update_database(user: dict = Depends(get_current_user)):
    if not _is_clamav_installed():
        raise HTTPException(status_code=400, detail="ClamAV not installed")

    result = utils.run_command(["freshclam"], check=False, timeout=120)
    success = result and hasattr(result, 'returncode') and result.returncode == 0
    return {"status": "updated" if success else "failed", "success": success}
