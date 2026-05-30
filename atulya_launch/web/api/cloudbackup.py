"""Cloud Backup API — GCS and Azure Blob Storage integration."""

import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/backups/cloud", tags=["cloud-backup"])

CLOUD_CONFIG_FILE = utils.CONFIG_DIR / "cloud_backup.json"


def _load_cloud_config() -> dict:
    if CLOUD_CONFIG_FILE.exists():
        with open(CLOUD_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_cloud_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CLOUD_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _gcloud_available() -> bool:
    return shutil.which("gcloud") is not None


def _az_available() -> bool:
    return shutil.which("az") is not None


def _rclone_available() -> bool:
    return shutil.which("rclone") is not None


def _gcs_upload(bucket: str, local_path: str, remote_path: str, credential_file: Optional[str] = None) -> dict:
    cmd = ["gsutil"]
    if credential_file:
        cmd.extend(["-o", f"GSUtil:service_account_json_key_file={credential_file}"])
    cmd.extend(["-m", "cp", "-r", local_path, f"gs://{bucket}/{remote_path}"])
    result = utils.run_command(cmd, check=False)
    if result and result.returncode == 0:
        return {"status": "uploaded", "provider": "gcs", "bucket": bucket, "remote_path": remote_path}
    return {"error": result.stderr if result else "GCS upload failed"}


def _gcs_download(bucket: str, remote_path: str, local_path: str, credential_file: Optional[str] = None) -> dict:
    cmd = ["gsutil"]
    if credential_file:
        cmd.extend(["-o", f"GSUtil:service_account_json_key_file={credential_file}"])
    cmd.extend(["cp", "-r", f"gs://{bucket}/{remote_path}", local_path])
    result = utils.run_command(cmd, check=False)
    if result and result.returncode == 0:
        return {"status": "downloaded", "provider": "gcs", "local_path": local_path}
    return {"error": result.stderr if result else "GCS download failed"}


def _gcs_list(bucket: str, prefix: str = "", credential_file: Optional[str] = None) -> list:
    cmd = ["gsutil", "ls"]
    if credential_file:
        cmd.extend(["-o", f"GSUtil:service_account_json_key_file={credential_file}"])
    cmd.append(f"gs://{bucket}/{prefix}*")
    result = utils.run_command(cmd, check=False)
    if not result or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _azure_upload(storage_account: str, container: str, local_path: str, remote_path: str, key: Optional[str] = None) -> dict:
    cmd = ["az", "storage", "blob", "upload", "--account-name", storage_account, "--container-name", container, "--name", remote_path, "--file", local_path, "--overwrite"]
    if key:
        cmd.extend(["--account-key", key])
    result = utils.run_command(cmd, check=False)
    if result and result.returncode == 0:
        return {"status": "uploaded", "provider": "azure", "container": container, "remote_path": remote_path}
    return {"error": result.stderr if result else "Azure upload failed"}


def _azure_download(storage_account: str, container: str, remote_path: str, local_path: str, key: Optional[str] = None) -> dict:
    cmd = ["az", "storage", "blob", "download", "--account-name", storage_account, "--container-name", container, "--name", remote_path, "--file", local_path, "--overwrite"]
    if key:
        cmd.extend(["--account-key", key])
    result = utils.run_command(cmd, check=False)
    if result and result.returncode == 0:
        return {"status": "downloaded", "provider": "azure", "local_path": local_path}
    return {"error": result.stderr if result else "Azure download failed"}


def _azure_list(storage_account: str, container: str, prefix: str = "", key: Optional[str] = None) -> list:
    cmd = ["az", "storage", "blob", "list", "--account-name", storage_account, "--container-name", container, "--prefix", prefix, "--output", "json"]
    if key:
        cmd.extend(["--account-key", key])
    result = utils.run_command(cmd, check=False)
    if not result or result.returncode != 0:
        return []
    try:
        blobs = json.loads(result.stdout)
        return [{"name": b["name"], "size": b.get("properties", {}).get("contentLength", 0)} for b in blobs]
    except (json.JSONDecodeError, KeyError):
        return []


class GCSConfig(BaseModel):
    provider: str = "gcs"
    bucket: str
    credential_file: Optional[str] = None


class AzureConfig(BaseModel):
    provider: str = "azure"
    storage_account: str
    container: str
    access_key: Optional[str] = None


class CloudPush(BaseModel):
    local_path: str
    remote_path: str


class CloudPull(BaseModel):
    remote_path: str
    local_path: str


@router.get("/config")
def get_cloud_config(user: dict = Depends(get_current_user)):
    config = _load_cloud_config()
    return {
        "providers": config,
        "gcloud_available": _gcloud_available(),
        "az_available": _az_available(),
        "rclone_available": _rclone_available(),
    }


@router.post("/config")
def set_cloud_config(body: GCSConfig | AzureConfig, user: dict = Depends(get_current_user)):
    config = _load_cloud_config()
    provider_key = body.provider

    if provider_key == "gcs":
        if not _gcloud_available():
            raise HTTPException(status_code=400, detail="gcloud CLI is not installed")
        config["gcs"] = {
            "provider": "gcs",
            "bucket": body.bucket,
            "credential_file": body.credential_file,
            "updated_at": datetime.now().isoformat(),
        }
    elif provider_key == "azure":
        if not _az_available():
            raise HTTPException(status_code=400, detail="Azure CLI is not installed")
        config["azure"] = {
            "provider": "azure",
            "storage_account": body.storage_account,
            "container": body.container,
            "access_key": body.access_key,
            "updated_at": datetime.now().isoformat(),
        }
    else:
        raise HTTPException(status_code=400, detail="Provider must be 'gcs' or 'azure'")

    _save_cloud_config(config)
    return {"status": "configured", "provider": provider_key}


@router.post("/push")
def cloud_push(body: CloudPush, user: dict = Depends(get_current_user)):
    config = _load_cloud_config()
    from pathlib import Path
    if not Path(body.local_path).exists():
        raise HTTPException(status_code=404, detail="Local path not found")

    gcs = config.get("gcs")
    azure = config.get("azure")

    if gcs:
        result = _gcs_upload(gcs["bucket"], body.local_path, body.remote_path, gcs.get("credential_file"))
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    if azure:
        result = _azure_upload(azure["storage_account"], azure["container"], body.local_path, body.remote_path, azure.get("access_key"))
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    raise HTTPException(status_code=400, detail="No cloud provider configured")


@router.post("/pull")
def cloud_pull(body: CloudPull, user: dict = Depends(get_current_user)):
    config = _load_cloud_config()

    gcs = config.get("gcs")
    azure = config.get("azure")

    if gcs:
        result = _gcs_download(gcs["bucket"], body.remote_path, body.local_path, gcs.get("credential_file"))
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    if azure:
        result = _azure_download(azure["storage_account"], azure["container"], body.remote_path, body.local_path, azure.get("access_key"))
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result

    raise HTTPException(status_code=400, detail="No cloud provider configured")


@router.get("/list")
def cloud_list(user: dict = Depends(get_current_user)):
    config = _load_cloud_config()

    gcs = config.get("gcs")
    azure = config.get("azure")

    if gcs:
        items = _gcs_list(gcs["bucket"], credential_file=gcs.get("credential_file"))
        return {"provider": "gcs", "bucket": gcs["bucket"], "items": items}

    if azure:
        items = _azure_list(azure["storage_account"], azure["container"], key=azure.get("access_key"))
        return {"provider": "azure", "container": azure["container"], "items": items}

    raise HTTPException(status_code=400, detail="No cloud provider configured")
