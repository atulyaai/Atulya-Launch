"""Database management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/databases", tags=["databases"])


class DatabaseCreate(BaseModel):
    name: str
    user: Optional[str] = None
    password: Optional[str] = None
    db_type: str = "mysql"


class RestoreRequest(BaseModel):
    backup_path: str


@router.get("")
def list_databases(user: dict = Depends(get_current_user)):
    return {"databases": core.db_list()}


@router.post("")
def create_database(body: DatabaseCreate, user: dict = Depends(get_current_user)):
    result = core.db_create(
        db_name=body.name,
        db_user=body.user,
        db_password=body.password,
        db_type=body.db_type,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"database": result}


@router.delete("/{name}")
def delete_database(name: str, user: dict = Depends(get_current_user)):
    dbs = core.db_list()
    if name not in dbs:
        raise HTTPException(status_code=404, detail="Database not found")
    db_type = dbs[name].get("type", "mysql")
    if db_type == "mysql":
        result = utils.run_command(["mysql", "-e", f"DROP DATABASE IF EXISTS `{name}`;"], check=False)
    elif db_type == "postgresql":
        result = utils.run_command(["sudo", "-u", "postgres", "psql", "-c", f"DROP DATABASE IF EXISTS {name};"], check=False)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported db type: {db_type}")
    all_config = utils.load_config()
    all_config.get("databases", {}).pop(name, None)
    utils.save_config(all_config)
    return {"status": "deleted", "name": name}


@router.post("/{name}/backup")
def backup_database(name: str, user: dict = Depends(get_current_user)):
    result = core.db_backup(name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{name}/restore")
def restore_database(name: str, body: RestoreRequest, user: dict = Depends(get_current_user)):
    dbs = core.db_list()
    db_type = dbs.get(name, {}).get("type", "mysql")
    result = core.db_restore(name, body.backup_path, db_type)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/{name}/phpmyadmin")
def get_phpmyadmin_url(name: str, user: dict = Depends(get_current_user)):
    dbs = core.db_list()
    if name not in dbs:
        raise HTTPException(status_code=404, detail="Database not found")
    return {"url": "/phpmyadmin", "database": name}
