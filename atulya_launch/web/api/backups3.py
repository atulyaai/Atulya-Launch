"""S3/Remote backup API."""

import os
import json
import subprocess
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/backups/remote", tags=["backups-remote"])

S3_CONFIG_FILE = utils.CONFIG_DIR / "s3_backup.json"


def _load_s3_config() -> dict:
    if S3_CONFIG_FILE.exists():
        with open(S3_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_s3_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(S3_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


class S3Config(BaseModel):
    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    endpoint: Optional[str] = None
    prefix: str = "atulya-backups"


class PushRequest(BaseModel):
    backup_name: Optional[str] = None


class PullRequest(BaseModel):
    remote_key: str


@router.get("/config")
def get_s3_config(user: dict = Depends(get_current_user)):
    config = _load_s3_config()
    if config.get("secret_key"):
        config["secret_key"] = "***" + config["secret_key"][-4:] if len(config["secret_key"]) > 4 else "***"
    return {"config": config}


@router.post("/config")
def set_s3_config(body: S3Config, user: dict = Depends(get_current_user)):
    config = {
        "bucket": body.bucket,
        "access_key": body.access_key,
        "secret_key": body.secret_key,
        "region": body.region,
        "endpoint": body.endpoint,
        "prefix": body.prefix,
    }
    _save_s3_config(config)
    # Write AWS credentials file
    if utils.is_linux():
        aws_dir = os.path.expanduser("~/.aws")
        os.makedirs(aws_dir, exist_ok=True)
        creds_file = os.path.join(aws_dir, "credentials")
        creds_content = (
            f"[atulya-backup]\n"
            f"aws_access_key_id = {body.access_key}\n"
            f"aws_secret_access_key = {body.secret_key}\n"
        )
        with open(creds_file, "w") as f:
            f.write(creds_content)
        # Write config
        config_file = os.path.join(aws_dir, "config")
        config_content = (
            f"[atulya-backup]\n"
            f"region = {body.region}\n"
        )
        if body.endpoint:
            config_content += f"endpoint_url = {body.endpoint}\n"
        with open(config_file, "w") as f:
            f.write(config_content)
    return {"status": "S3 config saved"}


@router.post("/push")
def push_backup(body: PushRequest, user: dict = Depends(get_current_user)):
    config = _load_s3_config()
    if not config.get("bucket"):
        raise HTTPException(status_code=400, detail="S3 not configured")
    backup_dir = utils.CONFIG_DIR / "backups"
    if body.backup_name:
        backup_path = backup_dir / body.backup_name
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup not found")
        backup_name = body.backup_name
    else:
        # Use latest backup
        backups = sorted(backup_dir.iterdir()) if backup_dir.exists() else []
        if not backups:
            raise HTTPException(status_code=404, detail="No backups found")
        backup_path = backups[-1]
        backup_name = backups[-1].name
    s3_uri = f"s3://{config['bucket']}/{config.get('prefix', 'atulya-backups')}/{backup_name}"
    endpoint = config.get("endpoint", "")
    cmd = [
        "aws", "s3", "cp",
        "--profile", "atulya-backup",
        str(backup_path),
        s3_uri,
        "--recursive",
    ]
    if endpoint:
        cmd.extend(["--endpoint-url", endpoint])
    result = utils.run_command(cmd, check=False, timeout=300)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Push failed: {result.stderr or 'unknown error'}")
    return {"status": "pushed", "backup": backup_name, "s3_uri": s3_uri}


@router.post("/pull")
def pull_backup(body: PullRequest, user: dict = Depends(get_current_user)):
    config = _load_s3_config()
    if not config.get("bucket"):
        raise HTTPException(status_code=400, detail="S3 not configured")
    s3_uri = f"s3://{config['bucket']}/{body.remote_key}"
    local_path = utils.CONFIG_DIR / "backups" / body.remote_key.split("/")[-1]
    local_path.mkdir(parents=True, exist_ok=True)
    endpoint = config.get("endpoint", "")
    cmd = [
        "aws", "s3", "cp",
        "--profile", "atulya-backup",
        s3_uri,
        str(local_path),
        "--recursive",
    ]
    if endpoint:
        cmd.extend(["--endpoint-url", endpoint])
    result = utils.run_command(cmd, check=False, timeout=300)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Pull failed: {result.stderr or 'unknown error'}")
    return {"status": "pulled", "backup": body.remote_key, "local_path": str(local_path)}


@router.get("/list")
def list_remote_backups(user: dict = Depends(get_current_user)):
    config = _load_s3_config()
    if not config.get("bucket"):
        raise HTTPException(status_code=400, detail="S3 not configured")
    s3_prefix = f"s3://{config['bucket']}/{config.get('prefix', 'atulya-backups')}/"
    endpoint = config.get("endpoint", "")
    cmd = [
        "aws", "s3", "ls",
        "--profile", "atulya-backup",
        s3_prefix,
        "--recursive",
    ]
    if endpoint:
        cmd.extend(["--endpoint-url", endpoint])
    result = utils.run_command(cmd, check=False)
    backups = []
    if result and result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 4:
                backups.append({
                    "key": " ".join(parts[3:]),
                    "size": int(parts[2]) if parts[2].isdigit() else 0,
                    "last_modified": f"{parts[0]} {parts[1]}",
                })
    return {"backups": backups}
