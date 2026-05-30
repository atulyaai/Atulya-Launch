"""Remote database access configuration API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/databases/remote", tags=["databases-remote"])

REMOTE_DB_FILE = utils.CONFIG_DIR / "remote_db.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "bind_address": "127.0.0.1",
    "port": 3306,
    "allow_from": ["127.0.0.1"],
    "require_ssl": False,
}


def _load_config() -> dict:
    if REMOTE_DB_FILE.exists():
        with open(REMOTE_DB_FILE, "r") as f:
            return json.load(f) or DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def _save_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(REMOTE_DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


class RemoteDBConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    bind_address: Optional[str] = None
    port: Optional[int] = None
    allow_from: Optional[list] = None
    require_ssl: Optional[bool] = None


def _get_mysql_bind_address() -> str:
    result = utils.run_command(
        ["mysql", "-N", "-e", "SHOW VARIABLES LIKE 'bind_address';"],
        check=False,
    )
    if result and result.returncode == 0 and result.stdout.strip():
        parts = result.stdout.strip().split("\t")
        if len(parts) >= 2:
            return parts[1]
    return "127.0.0.1"


def _apply_mysql_remote_config(bind_address: str, port: int):
    my_cnf_path = "/etc/mysql/mysql.conf.d/mysqld.cnf"
    if not utils.is_linux():
        return

    import re
    try:
        with open(my_cnf_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        return

    content = re.sub(r"bind-address\s*=.*", f"bind-address = {bind_address}", content)
    content = re.sub(r"port\s*=.*", f"port = {port}", content)

    with open(my_cnf_path, "w") as f:
        f.write(content)

    utils.service_action("restart", "mysql")


def _apply_postgres_remote_config(bind_address: str, port: int):
    if not utils.is_linux():
        return

    postgres_conf = "/etc/postgresql/main/postgresql.conf"
    import re

    try:
        with open(postgres_conf, "r") as f:
            content = f.read()
    except FileNotFoundError:
        return

    content = re.sub(r"listen_addresses\s*=.*", f"listen_addresses = '{bind_address}'", content)
    content = re.sub(r"port\s*=.*", f"port = {port}", content)

    with open(postgres_conf, "w") as f:
        f.write(content)

    utils.service_action("restart", "postgresql")


def _apply_hba_rules(allow_from: list):
    if not utils.is_linux():
        return

    hba_path = "/etc/mysql/mysql.conf.d/mysqld.cnf"
    if not utils.is_linux():
        return

    result = utils.run_command(["mysql", "-N", "-e", "SELECT VERSION();"], check=False)
    is_mysql = result is not None and result.returncode == 0

    if is_mysql:
        for ip in allow_from:
            utils.run_command(
                ["mysql", "-e", f"GRANT ALL PRIVILEGES ON *.* TO '%'@'{ip}' WITH GRANT OPTION;"],
                check=False,
            )
        utils.run_command(["mysql", "-e", "FLUSH PRIVILEGES;"], check=False)


@router.get("/config")
def get_remote_config(user: dict = Depends(get_current_user)):
    config = _load_config()
    if utils.is_linux():
        config["current_mysql_bind"] = _get_mysql_bind_address()
    return {"config": config}


@router.put("/config")
def update_remote_config(body: RemoteDBConfigUpdate, user: dict = Depends(get_current_user)):
    config = _load_config()

    if body.enabled is not None:
        config["enabled"] = body.enabled
    if body.bind_address is not None:
        config["bind_address"] = body.bind_address
    if body.port is not None:
        config["port"] = body.port
    if body.allow_from is not None:
        config["allow_from"] = body.allow_from
    if body.require_ssl is not None:
        config["require_ssl"] = body.require_ssl

    _save_config(config)

    if utils.is_linux() and config["enabled"]:
        try:
            bind = config["bind_address"]
            if bind == "0.0.0.0" or bind == "all":
                bind = "0.0.0.0"
            _apply_mysql_remote_config(bind, config["port"])
            _apply_postgres_remote_config(bind, config["port"])
            if config.get("allow_from"):
                _apply_hba_rules(config["allow_from"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to apply remote access config: {e}")

    return {"status": "updated", "config": config}
