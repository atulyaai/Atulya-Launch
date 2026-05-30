"""Migration tool — import from cPanel, Plesk, and other panels."""

import datetime
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/migration", tags=["migration"])

MIGRATION_FILE = utils.CONFIG_DIR / "migration.json"


class MigrationStart(BaseModel):
    source_type: str
    backup_path: Optional[str] = None


def _load_migration() -> dict:
    if MIGRATION_FILE.exists():
        return json.loads(MIGRATION_FILE.read_text())
    return {"status": "idle", "history": []}


def _save_migration(data: dict):
    MIGRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    MIGRATION_FILE.write_text(json.dumps(data, indent=2))


def _extract_archive(archive_path: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tar:
            tar.extractall(str(dest))
    elif zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(str(dest))
    return dest


def _import_cpanel_data(backup_dir: Path) -> dict:
    results = {"sites": [], "databases": [], "emails": [], "dns": []}
    cpconf = backup_dir / "cp" / "cpconf"
    if cpconf.exists():
        users_dir = backup_dir / "cp" / "users"
        if users_dir.exists():
            for user_dir in users_dir.iterdir():
                if user_dir.is_dir():
                    _process_cpanel_user(user_dir, results)
    mysql_dir = backup_dir / "mysql"
    if mysql_dir.exists():
        for sql_file in mysql_dir.glob("*.sql*"):
            results["databases"].append(sql_file.name)
            db_name = sql_file.stem.replace(".sql", "")
            import_dir = utils.CONFIG_DIR / "imports"
            import_dir.mkdir(exist_ok=True)
            dest_file = import_dir / sql_file.name
            if not dest_file.exists():
                dest_file.write_bytes(sql_file.read_bytes())
    homedir = backup_dir / "homedir"
    if homedir.exists():
        public_html = homedir / "public_html"
        if public_html.exists():
            results["sites"].append(str(public_html))
    return results


def _process_cpanel_user(user_dir: Path, results: dict):
    backup_config = user_dir / "backup-config"
    if backup_config.exists():
        try:
            config = json.loads(backup_config.read_text())
            if config.get("db"):
                results["databases"].extend(config["db"])
        except (json.JSONDecodeError, OSError):
            pass
    meta = user_dir / "meta"
    if meta.exists():
        try:
            meta_data = json.loads(meta.read_text())
            if meta_data.get("domain"):
                results["sites"].append(meta_data["domain"])
        except (json.JSONDecodeError, OSError):
            pass


def _import_plesk_data(backup_dir: Path) -> dict:
    results = {"sites": [], "databases": [], "emails": [], "dns": []}
    domains_xml = backup_dir / "domains.xml"
    if domains_xml.exists():
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(str(domains_xml))
            for domain_elem in tree.iter("domain"):
                name = domain_elem.get("name", "")
                if name:
                    results["sites"].append(name)
        except ET.ParseError:
            pass
    dumps_dir = backup_dir / "dumps"
    if dumps_dir.exists():
        for sql_file in dumps_dir.glob("*.sql*"):
            results["databases"].append(sql_file.name)
    return results


def _import_virtualmin_data(backup_dir: Path) -> dict:
    results = {"sites": [], "databases": [], "emails": [], "dns": []}
    for domain_dir in backup_dir.iterdir():
        if domain_dir.is_dir():
            server_conf = domain_dir / "server.conf"
            if server_conf.exists():
                results["sites"].append(domain_dir.name)
            mysql_dir = domain_dir / "mysql"
            if mysql_dir.exists():
                for sql_file in mysql_dir.glob("*.sql*"):
                    results["databases"].append(sql_file.name)
    return results


@router.post("/import-cpanel")
async def import_cpanel(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    import_dir = utils.CONFIG_DIR / "migration" / "cpanel"
    import_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = import_dir / f"cpanel_backup_{timestamp}.tar.gz"
    archive_path.write_bytes(content)
    extract_dir = import_dir / f"extracted_{timestamp}"
    try:
        _extract_archive(str(archive_path), extract_dir)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract archive: {str(e)}")
    results = _import_cpanel_data(extract_dir)
    data = _load_migration()
    data["status"] = "completed"
    data.setdefault("history", []).append({
        "type": "cpanel",
        "filename": file.filename,
        "timestamp": datetime.datetime.now().isoformat(),
        "results": results,
    })
    _save_migration(data)
    return {"status": "imported", "results": results}


@router.post("/import-plesk")
async def import_plesk(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    import_dir = utils.CONFIG_DIR / "migration" / "plesk"
    import_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = import_dir / f"plesk_backup_{timestamp}.tar.gz"
    archive_path.write_bytes(content)
    extract_dir = import_dir / f"extracted_{timestamp}"
    try:
        _extract_archive(str(archive_path), extract_dir)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract archive: {str(e)}")
    results = _import_plesk_data(extract_dir)
    data = _load_migration()
    data["status"] = "completed"
    data.setdefault("history", []).append({
        "type": "plesk",
        "filename": file.filename,
        "timestamp": datetime.datetime.now().isoformat(),
        "results": results,
    })
    _save_migration(data)
    return {"status": "imported", "results": results}


@router.post("/import-virtualmin")
async def import_virtualmin(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    import_dir = utils.CONFIG_DIR / "migration" / "virtualmin"
    import_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = import_dir / f"virtualmin_backup_{timestamp}.tar.gz"
    archive_path.write_bytes(content)
    extract_dir = import_dir / f"extracted_{timestamp}"
    try:
        _extract_archive(str(archive_path), extract_dir)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract archive: {str(e)}")
    results = _import_virtualmin_data(extract_dir)
    data = _load_migration()
    data["status"] = "completed"
    data.setdefault("history", []).append({
        "type": "virtualmin",
        "filename": file.filename,
        "timestamp": datetime.datetime.now().isoformat(),
        "results": results,
    })
    _save_migration(data)
    return {"status": "imported", "results": results}


@router.get("/status")
def migration_status(user: dict = Depends(get_current_user)):
    data = _load_migration()
    return {
        "status": data.get("status", "idle"),
        "last_migration": data.get("history", [])[-1] if data.get("history") else None,
    }


@router.get("/history")
def migration_history(user: dict = Depends(get_current_user)):
    data = _load_migration()
    return {"history": data.get("history", [])}
