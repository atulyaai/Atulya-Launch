"""Database user permissions management API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/databases/{db_name}/users", tags=["db-users"])


class DBUserGrant(BaseModel):
    username: str
    password: Optional[str] = None
    host: str = "localhost"
    permissions: list = ["ALL PRIVILEGES"]


class DBUserPermissionsUpdate(BaseModel):
    permissions: list
    host: str = "localhost"


def _get_db_type(db_name: str) -> str:
    config = utils.load_config()
    dbs = config.get("databases", {})
    if db_name in dbs:
        return dbs[db_name].get("type", "mysql")
    return "mysql"


def _get_mysql_grants(db_name: str, username: str, host: str) -> dict:
    sql = f"SHOW GRANTS FOR '{username}'@'{host}';"
    result = utils.run_command(["mysql", "-N", "-e", sql], check=False)
    if result and result.returncode == 0:
        grants = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                grants.append(line)
        return {"grants": grants}
    return {"grants": []}


def _get_postgres_grants(db_name: str, username: str) -> dict:
    sql = f"SELECT grantee, privilege_type, table_name FROM information_schema.role_table_grants WHERE grantee = '{username}' AND table_schema = 'public';"
    result = utils.run_command(
        ["sudo", "-u", "postgres", "psql", "-d", db_name, "-t", "-A", "-c", sql],
        check=False,
    )
    if result and result.returncode == 0:
        grants = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 3:
                    grants.append({
                        "grantee": parts[0],
                        "privilege": parts[1],
                        "table": parts[2],
                    })
        return {"grants": grants}
    return {"grants": []}


@router.get("")
def list_db_users(db_name: str, user: dict = Depends(get_current_user)):
    db_type = _get_db_type(db_name)

    if db_type == "mysql":
        result = utils.run_command(
            ["mysql", "-N", "-e", "SELECT User, Host FROM mysql.user;"],
            check=False,
        )
        users = []
        if result and result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        users.append({"username": parts[0], "host": parts[1]})
        return {"database": db_name, "users": users, "type": db_type}

    elif db_type == "postgresql":
        result = utils.run_command(
            ["sudo", "-u", "postgres", "psql", "-d", db_name, "-t", "-A", "-c",
             "SELECT rolname FROM pg_roles WHERE rolcanlogin = true;"],
            check=False,
        )
        users = []
        if result and result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line and line.strip():
                    users.append({"username": line.strip(), "host": "localhost"})
        return {"database": db_name, "users": users, "type": db_type}

    return {"database": db_name, "users": [], "type": db_type}


@router.post("")
def grant_db_user(db_name: str, body: DBUserGrant, user: dict = Depends(get_current_user)):
    db_type = _get_db_type(db_name)

    if not body.password:
        body.password = utils.generate_password(16)

    if db_type == "mysql":
        perms = ", ".join(body.permissions) if body.permissions else "ALL PRIVILEGES"
        sql = f"CREATE USER IF NOT EXISTS '{body.username}'@'{body.host}' IDENTIFIED BY '{body.password}';"
        result = utils.run_command(["mysql", "-e", sql], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to create user: {result.stderr}")

        sql = f"GRANT {perms} ON `{db_name}`.* TO '{body.username}'@'{body.host}';"
        result = utils.run_command(["mysql", "-e", sql], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to grant permissions: {result.stderr}")

        utils.run_command(["mysql", "-e", "FLUSH PRIVILEGES;"], check=False)

    elif db_type == "postgresql":
        sql = f"CREATE USER {body.username} WITH PASSWORD '{body.password}';"
        utils.run_command(["sudo", "-u", "postgres", "psql", "-c", sql], check=False)

        for perm in (body.permissions or ["ALL"]):
            perm_upper = perm.upper().replace(" PRIVILEGES", "")
            if perm_upper == "ALL" or perm_upper == "ALL PRIVILEGES":
                sql = f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {body.username};"
                utils.run_command(["sudo", "-u", "postgres", "psql", "-c", sql], check=False)
                sql = f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {body.username};"
                utils.run_command(["sudo", "-u", "postgres", "psql", "-d", db_name, "-c", sql], check=False)
            else:
                sql = f"GRANT {perm_upper} ON ALL TABLES IN SCHEMA public TO {body.username};"
                utils.run_command(["sudo", "-u", "postgres", "psql", "-d", db_name, "-c", sql], check=False)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported database type: {db_type}")

    return {
        "status": "granted",
        "database": db_name,
        "username": body.username,
        "host": body.host,
        "permissions": body.permissions,
    }


@router.delete("/{username}")
def revoke_db_user(db_name: str, username: str, user: dict = Depends(get_current_user)):
    db_type = _get_db_type(db_name)
    host = "localhost"

    if db_type == "mysql":
        sql = f"DROP USER IF EXISTS '{username}'@'{host}';"
        result = utils.run_command(["mysql", "-e", sql], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to revoke user: {result.stderr}")
        utils.run_command(["mysql", "-e", "FLUSH PRIVILEGES;"], check=False)

    elif db_type == "postgresql":
        sql = f"DROP OWNED BY {username}; DROP USER IF EXISTS {username};"
        utils.run_command(["sudo", "-u", "postgres", "psql", "-c", sql], check=False)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported database type: {db_type}")

    return {"status": "revoked", "database": db_name, "username": username}


@router.put("/{username}/permissions")
def update_db_user_permissions(db_name: str, username: str, body: DBUserPermissionsUpdate, user: dict = Depends(get_current_user)):
    db_type = _get_db_type(db_name)

    if db_type == "mysql":
        sql = f"REVOKE ALL PRIVILEGES ON `{db_name}`.* FROM '{username}'@'{body.host}';"
        utils.run_command(["mysql", "-e", sql], check=False)

        perms = ", ".join(body.permissions) if body.permissions else "ALL PRIVILEGES"
        sql = f"GRANT {perms} ON `{db_name}`.* TO '{username}'@'{body.host}';"
        result = utils.run_command(["mysql", "-e", sql], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to update permissions: {result.stderr}")

        utils.run_command(["mysql", "-e", "FLUSH PRIVILEGES;"], check=False)

    elif db_type == "postgresql":
        for perm in body.permissions:
            perm_upper = perm.upper().replace(" PRIVILEGES", "")
            if perm_upper == "ALL" or perm_upper == "ALL PRIVILEGES":
                sql = f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {username};"
                utils.run_command(["sudo", "-u", "postgres", "psql", "-c", sql], check=False)
            else:
                sql = f"GRANT {perm_upper} ON ALL TABLES IN SCHEMA public TO {username};"
                utils.run_command(["sudo", "-u", "postgres", "psql", "-d", db_name, "-c", sql], check=False)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported database type: {db_type}")

    return {"status": "updated", "database": db_name, "username": username, "permissions": body.permissions}


@router.get("/{username}/permissions")
def get_db_user_permissions(db_name: str, username: str, user: dict = Depends(get_current_user)):
    db_type = _get_db_type(db_name)
    host = "localhost"

    if db_type == "mysql":
        grants = _get_mysql_grants(db_name, username, host)
    elif db_type == "postgresql":
        grants = _get_postgres_grants(db_name, username)
    else:
        grants = {"grants": []}

    return {"database": db_name, "username": username, "permissions": grants}
