"""Backup management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import core
from atulya_launch.web.auth import get_current_user
from atulya_launch.web import backup_service

router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.get("")
def list_backups(user: dict = Depends(get_current_user)):
    return {"backups": backup_service.list_backups()}


@router.post("/create")
def create_backup(user: dict = Depends(get_current_user)):
    result = backup_service.create_backup()
    return {"backup": result}


@router.post("/restore/{name}")
def restore_backup(name: str, user: dict = Depends(get_current_user)):
    backups = backup_service.list_backups()
    if name not in backups:
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        result = backup_service.restore_backup(name)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@router.delete("/{name}")
def delete_backup(name: str, user: dict = Depends(get_current_user)):
    ok = backup_service.delete_backup(name)
    if not ok:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "deleted", "name": name}


@router.get("/schedule")
def get_schedule(user: dict = Depends(get_current_user)):
    schedules = core.backup_schedule_list()
    return {"schedules": schedules}


@router.post("/schedule")
def set_schedule(domain: str, schedule_type: str = "daily", retention: int = 7, time_str: str = "02:00", user: dict = Depends(get_current_user)):
    result = core.backup_schedule_create(
        domain=domain,
        schedule_type=schedule_type,
        retention=retention,
        time_str=time_str,
    )
    return {"schedule": result}
