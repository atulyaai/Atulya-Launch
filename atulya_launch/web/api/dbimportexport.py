"""Database import / export / scheduled export API."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/databases", tags=["db-import-export"])

EXPORT_FILE = utils.CONFIG_DIR / "db_exports.json"


class ExportSchedule(BaseModel):
    db_name: str
    interval: str = "daily"
    time: str = "03:00"
    keep_days: int = 7
    enabled: bool = True


def _load_exports() -> dict:
    if EXPORT_FILE.exists():
        import json
        return json.loads(EXPORT_FILE.read_text())
    return {"schedules": {}, "history": []}


def _save_exports(data: dict):
    EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    EXPORT_FILE.write_text(json.dumps(data, indent=2))


def _get_db_config(db_name: str) -> dict:
    dbs = utils.load_config().get("databases", {})
    if db_name not in dbs:
        return {}
    return dbs[db_name]


@router.post("/{db_name}/import")
async def import_database(db_name: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    db_config = _get_db_config(db_name)
    if not db_config:
        raise HTTPException(status_code=404, detail="Database not found")
    db_type = db_config.get("type", "mysql")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    import_dir = utils.CONFIG_DIR / "imports"
    import_dir.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "sql"
    file_path = import_dir / f"{db_name}_{timestamp}.{file_ext}"
    file_path.write_bytes(content)
    if file_ext == "gz":
        import_cmd = f"gunzip < {file_path} | {db_type} {db_name}"
    else:
        import_cmd = f"{db_type} {db_name} < {file_path}"
    if db_type == "mysql":
        result = utils.run_command(import_cmd, check=False, timeout=600)
    elif db_type == "postgresql":
        import_cmd = import_cmd.replace(db_type, f"sudo -u postgres psql {db_name} <")
        result = utils.run_command(import_cmd, check=False, timeout=600)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported db type: {db_type}")
    if not result or result.returncode != 0:
        detail = result.stderr if result else "Import failed"
        raise HTTPException(status_code=500, detail=detail)
    data = _load_exports()
    data.setdefault("history", []).append({
        "action": "import",
        "db_name": db_name,
        "filename": file.filename,
        "timestamp": datetime.datetime.now().isoformat(),
    })
    _save_exports(data)
    return {"status": "imported", "database": db_name, "filename": file.filename}


@router.get("/{db_name}/export")
def export_database(db_name: str, user: dict = Depends(get_current_user)):
    db_config = _get_db_config(db_name)
    if not db_config:
        raise HTTPException(status_code=404, detail="Database not found")
    db_type = db_config.get("type", "mysql")
    export_dir = utils.CONFIG_DIR / "exports"
    export_dir.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = export_dir / f"{db_name}_{timestamp}.sql"
    if db_type == "mysql":
        cmd = f"mysqldump {db_name} > {output_file}"
    elif db_type == "postgresql":
        cmd = f"sudo -u postgres pg_dump {db_name} > {output_file}"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported db type: {db_type}")
    result = utils.run_command(cmd, check=False, timeout=600)
    if not result or result.returncode != 0:
        detail = result.stderr if result else "Export failed"
        raise HTTPException(status_code=500, detail=detail)
    file_size = output_file.stat().st_size if output_file.exists() else 0
    data = _load_exports()
    data.setdefault("history", []).append({
        "action": "export",
        "db_name": db_name,
        "file": str(output_file),
        "size": file_size,
        "timestamp": datetime.datetime.now().isoformat(),
    })
    _save_exports(data)
    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(output_file),
        filename=f"{db_name}_{timestamp}.sql",
        media_type="application/sql",
    )


@router.post("/{db_name}/export/schedule")
def schedule_export(db_name: str, body: ExportSchedule, user: dict = Depends(get_current_user)):
    db_config = _get_db_config(db_name)
    if not db_config:
        raise HTTPException(status_code=404, detail="Database not found")
    if body.interval not in ("hourly", "daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="Interval must be: hourly, daily, weekly, monthly")
    script_path = utils.CONFIG_DIR / "scripts" / f"export_{db_name}.sh"
    script_path.parent.mkdir(exist_ok=True)
    db_type = db_config.get("type", "mysql")
    export_dir = utils.CONFIG_DIR / "exports"
    export_dir.mkdir(exist_ok=True)
    if db_type == "mysql":
        dump_cmd = f"mysqldump {db_name}"
    else:
        dump_cmd = f"sudo -u postgres pg_dump {db_name}"
    script_content = (
        f"#!/bin/bash\n"
        f"TIMESTAMP=$(date +%Y%m%d_%H%M%S)\n"
        f"OUTPUT={export_dir}/{db_name}_$TIMESTAMP.sql\n"
        f"{dump_cmd} > $OUTPUT\n"
        f"find {export_dir} -name '{db_name}_*.sql' -mtime +{body.keep_days} -delete\n"
    )
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    cron_map = {
        "hourly": "0 * * * *",
        "daily": f"{body.time} * * *",
        "weekly": f"{body.time} * * 0",
        "monthly": f"{body.time} 1 * *",
    }
    cron_line = f"{cron_map[body.interval]} {script_path}"
    temp_cron = utils.CONFIG_DIR / "temp_cron"
    result = utils.run_command(
        f"crontab -l > {temp_cron} 2>/dev/null; echo '{cron_line}' >> {temp_cron}; crontab {temp_cron}",
        check=False,
    )
    schedule_id = f"{db_name}_{body.interval}"
    data = _load_exports()
    data.setdefault("schedules", {})[schedule_id] = {
        "id": schedule_id,
        "db_name": db_name,
        "interval": body.interval,
        "time": body.time,
        "keep_days": body.keep_days,
        "enabled": body.enabled,
        "script": str(script_path),
        "created_at": datetime.datetime.now().isoformat(),
    }
    _save_exports(data)
    return {"status": "scheduled", "schedule_id": schedule_id}


@router.get("/export/schedules")
def list_schedules(user: dict = Depends(get_current_user)):
    data = _load_exports()
    return {"schedules": data.get("schedules", {})}


@router.get("/export/history")
def export_history(user: dict = Depends(get_current_user)):
    data = _load_exports()
    return {"history": data.get("history", [])[-50:]}
