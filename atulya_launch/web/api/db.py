"""Database management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/databases", tags=["databases"])


class DatabaseCreate(BaseModel):
    name: str
    db_type: str = "mysql"


class RestoreRequest(BaseModel):
    backup_path: str


@router.get("")
def list_databases(user: dict = Depends(get_current_user)):
    return {"databases": core.db_list()}


@router.post("")
def create_database(body: DatabaseCreate, user: dict = Depends(get_current_user)):
    result = core.database_create(name=body.name, db_type=body.db_type)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"database": result}


@router.delete("/{name}")
def delete_database(name: str, user: dict = Depends(get_current_user)):
    dbs = core.db_list()
    if name not in dbs:
        raise HTTPException(status_code=404, detail="Database not found")
    db_type = dbs[name].get("db_type", "mysql")
    if db_type == "mysql":
        utils.run_command(["mysql", "-e", f"DROP DATABASE IF EXISTS `{name}`;"], check=False)
    elif db_type == "postgresql":
        utils.run_command(["sudo", "-u", "postgres", "psql", "-c", f"DROP DATABASE IF EXISTS {name};"], check=False)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported db type: {db_type}")
    from atulya_launch.web.database import connect
    conn = connect()
    try:
        conn.execute("DELETE FROM databases WHERE name = ?", (name,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "deleted", "name": name}


@router.post("/{name}/backup")
def backup_database(name: str, user: dict = Depends(get_current_user)):
    dbs = core.db_list()
    db_type = dbs.get(name, {}).get("db_type", "mysql")
    result = core.database_backup(name=name, db_type=db_type)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{name}/restore")
def restore_database(name: str, body: RestoreRequest, user: dict = Depends(get_current_user)):
    dbs = core.db_list()
    db_type = dbs.get(name, {}).get("db_type", "mysql")
    if db_type == "mysql":
        result = utils.run_command(
            ["mysql", name, "<", body.backup_path], check=False
        )
    elif db_type == "postgresql":
        result = utils.run_command(
            ["sudo", "-u", "postgres", "psql", "-d", name, "-f", body.backup_path], check=False
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported db type: {db_type}")
    return {"status": "restored", "name": name}


@router.get("/{name}/phpmyadmin")
def get_phpmyadmin_url(name: str, user: dict = Depends(get_current_user)):
    dbs = core.db_list()
    if name not in dbs:
        raise HTTPException(status_code=404, detail="Database not found")
    return {"url": "/phpmyadmin", "database": name}
