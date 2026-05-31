"""Staging/clone environment API."""

import os
import shutil
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/staging", tags=["staging"])

STAGING_FILE = utils.CONFIG_DIR / "staging.json"


def _load_staging() -> dict:
    if STAGING_FILE.exists():
        with open(STAGING_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_staging(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(STAGING_FILE, "w") as f:
        json.dump(data, f, indent=2)


class CloneSiteRequest(BaseModel):
    source_domain: str
    staging_domain: str


class PushRequest(BaseModel):
    staging_id: str


class PullRequest(BaseModel):
    staging_id: str


@router.get("/list")
def list_staging(user: dict = Depends(get_current_user)):
    data = _load_staging()
    result = []
    for sid, entry in data.items():
        exists = os.path.isdir(entry.get("staging_path", ""))
        result.append({"id": sid, "status": "active" if exists else "missing", **entry})
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
    # Clone database if possible
    db_name = f"{body.source_domain.replace('.', '_')}_staging"
    db_user = f"{body.source_domain.replace('.', '_')}_staging"
    db_pass = utils.generate_password(20)
    db_created = False
    if utils.is_linux():
        # Copy site files
        if os.path.isdir(source_root):
            shutil.copytree(source_root, staging_root, dirs_exist_ok=True)
        # Try to clone database
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
            # Dump and restore
            utils.run_command(
                ["bash", "-c", f"mysqldump `{body.source_domain.replace('.', '_')}` | mysql `{db_name}`"],
                check=False,
            )
    staging_id = body.staging_domain.replace(".", "_")
    data = _load_staging()
    data[staging_id] = {
        "source_domain": body.source_domain,
        "staging_domain": body.staging_domain,
        "staging_path": staging_root,
        "source_path": source_root,
        "database": db_name if db_created else None,
        "created_by": user.get("sub", "admin"),
    }
    _save_staging(data)
    return {
        "status": "cloned",
        "staging_id": staging_id,
        "staging_domain": body.staging_domain,
        "database": db_name if db_created else None,
    }


@router.post("/push")
def push_to_production(body: PushRequest, user: dict = Depends(get_current_user)):
    data = _load_staging()
    if body.staging_id not in data:
        raise HTTPException(status_code=404, detail="Staging environment not found")
    entry = data[body.staging_id]
    staging_path = entry.get("staging_path", "")
    source_path = entry.get("source_path", "")
    if not os.path.isdir(staging_path):
        raise HTTPException(status_code=400, detail="Staging directory not found")
    if utils.is_linux():
        # Sync files from staging to production
        if os.path.isdir(source_path):
            utils.run_command(
                ["rsync", "-av", "--delete", staging_path + "/", source_path + "/"],
                check=False,
            )
        # Push database
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
    data = _load_staging()
    if body.staging_id not in data:
        raise HTTPException(status_code=404, detail="Staging environment not found")
    entry = data[body.staging_id]
    staging_path = entry.get("staging_path", "")
    source_path = entry.get("source_path", "")
    if not os.path.isdir(source_path):
        raise HTTPException(status_code=400, detail="Source directory not found")
    if utils.is_linux():
        # Sync files from production to staging
        os.makedirs(staging_path, exist_ok=True)
        utils.run_command(
            ["rsync", "-av", "--delete", source_path + "/", staging_path + "/"],
            check=False,
        )
        # Pull database
        db = entry.get("database")
        if db:
            prod_db = entry.get("source_domain", "").replace(".", "_")
            utils.run_command(
                ["bash", "-c", f"mysqldump `{prod_db}` | mysql `{db}`"],
                check=False,
            )
    return {"status": "pulled from production", "staging_id": body.staging_id}
