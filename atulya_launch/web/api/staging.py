"""Staging/clone environment API."""

import os
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/staging", tags=["staging"])


class CloneSiteRequest(BaseModel):
    source_domain: str
    staging_domain: str


class PushRequest(BaseModel):
    staging_id: str


class PullRequest(BaseModel):
    staging_id: str


@router.get("/list")
def list_staging(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, source_domain, staging_domain, staging_path, source_path, database, created_by FROM staging_environments",
        ).fetchall()
    result = []
    for r in rows:
        entry = dict(r)
        exists = os.path.isdir(entry.get("staging_path", ""))
        entry["status"] = "active" if exists else "missing"
        result.append(entry)
    return {"staging": result}


@router.post("/clone")
def clone_site(body: CloneSiteRequest, user: dict = Depends(get_current_user)):
    config = utils.load_config()
    sites = config.get("sites", {})
    if body.source_domain not in sites:
        raise HTTPException(status_code=404, detail="Source site not found")
    source_root = sites[body.source_domain].get("web_root", f"/var/www/{body.source_domain}/public")
    staging_root = f"/var/www/{body.staging_domain}/public"
    staging_data = utils.CONFIG_DIR / "staging" / body.staging_domain
    staging_data.mkdir(parents=True, exist_ok=True)
    db_name = f"{body.source_domain.replace('.', '_')}_staging"
    db_user = f"{body.source_domain.replace('.', '_')}_staging"
    db_pass = utils.generate_password(20)
    db_created = False
    if utils.is_linux():
        if os.path.isdir(source_root):
            shutil.copytree(source_root, staging_root, dirs_exist_ok=True)
        result = utils.run_command(
            ["mysql", "-e", f"CREATE DATABASE IF NOT EXISTS `{db_name}`"],
            check=False,
        )
        if result and result.returncode == 0:
            db_created = True
            utils.run_command(
                ["mysql", "-e", f"CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_pass}'"],
                check=False,
            )
            utils.run_command(
                ["mysql", "-e", f"GRANT ALL ON `{db_name}`.* TO '{db_user}'@'localhost'"],
                check=False,
            )
            utils.run_command(
                ["bash", "-c", f"mysqldump `{body.source_domain.replace('.', '_')}` | mysql `{db_name}`"],
                check=False,
            )
    staging_id = body.staging_domain.replace(".", "_")
    from datetime import datetime
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO staging_environments
               (id, source_domain, staging_domain, staging_path, source_path, database, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (staging_id, body.source_domain, body.staging_domain, staging_root, source_root,
             db_name if db_created else None, user.get("sub", "admin"), datetime.now().isoformat()),
        )
    return {
        "status": "cloned",
        "staging_id": staging_id,
        "staging_domain": body.staging_domain,
        "database": db_name if db_created else None,
    }


@router.post("/push")
def push_to_production(body: PushRequest, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM staging_environments WHERE id = ?", (body.staging_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Staging environment not found")
    entry = dict(row)
    staging_path = entry.get("staging_path", "")
    source_path = entry.get("source_path", "")
    if not os.path.isdir(staging_path):
        raise HTTPException(status_code=400, detail="Staging directory not found")
    if utils.is_linux():
        if os.path.isdir(source_path):
            utils.run_command(
                ["rsync", "-av", "--delete", staging_path + "/", source_path + "/"],
                check=False,
            )
        db = entry.get("database")
        if db:
            prod_db = entry.get("source_domain", "").replace(".", "_")
            utils.run_command(
                ["bash", "-c", f"mysqldump `{db}` | mysql `{prod_db}`"],
                check=False,
            )
    return {"status": "pushed to production", "staging_id": body.staging_id}


@router.post("/pull")
def pull_from_production(body: PullRequest, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM staging_environments WHERE id = ?", (body.staging_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Staging environment not found")
    entry = dict(row)
    staging_path = entry.get("staging_path", "")
    source_path = entry.get("source_path", "")
    if not os.path.isdir(source_path):
        raise HTTPException(status_code=400, detail="Source directory not found")
    if utils.is_linux():
        os.makedirs(staging_path, exist_ok=True)
        utils.run_command(
            ["rsync", "-av", "--delete", source_path + "/", staging_path + "/"],
            check=False,
        )
        db = entry.get("database")
        if db:
            prod_db = entry.get("source_domain", "").replace(".", "_")
            utils.run_command(
                ["bash", "-c", f"mysqldump `{prod_db}` | mysql `{db}`"],
                check=False,
            )
    return {"status": "pulled from production", "staging_id": body.staging_id}
