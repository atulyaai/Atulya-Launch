"""Backup management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/backups", tags=["backups"])


class BackupCreate(BaseModel):
    name: Optional[str] = None
    include_databases: bool = True
    include_sites: bool = True
    include_config: bool = True


class ScheduleSet(BaseModel):
    interval: str
    time: str = "02:00"
    enabled: bool = True
    keep_days: int = 30


@router.get("")
def list_backups(user: dict = Depends(get_current_user)):
    return {"backups": core.backup_list()}


@router.post("/create")
def create_backup(body: BackupCreate, user: dict = Depends(get_current_user)):
    result = core.backup_create(
        name=body.name,
        include_databases=body.include_databases,
        include_sites=body.include_sites,
        include_config=body.include_config,
    )
    return {"backup": result}


@router.post("/restore/{name}")
def restore_backup(name: str, user: dict = Depends(get_current_user)):
    backups = core.backup_list()
    if name not in backups:
        raise HTTPException(status_code=404, detail="Backup not found")
    result = core.backup_restore(name)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.delete("/{name}")
def delete_backup(name: str, user: dict = Depends(get_current_user)):
    backups = core.backup_list()
    if name not in backups:
        raise HTTPException(status_code=404, detail="Backup not found")
    import shutil
    backup_dir = utils.CONFIG_DIR / "backups" / name
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    return {"status": "deleted", "name": name}


@router.get("/schedule")
def get_schedule(user: dict = Depends(get_current_user)):
    config = utils.load_config()
    return {"schedule": config.get("backup_schedule", None)}


@router.post("/schedule")
def set_schedule(body: ScheduleSet, user: dict = Depends(get_current_user)):
    result = core.backup_schedule(
        interval=body.interval,
        time_str=body.time,
        enabled=body.enabled,
        keep_days=body.keep_days,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"schedule": result}
