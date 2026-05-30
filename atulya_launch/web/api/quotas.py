"""Disk quota management API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/quotas", tags=["quotas"])

QUOTAS_FILE = utils.CONFIG_DIR / "quotas.json"


def _load_quotas() -> dict:
    if QUOTAS_FILE.exists():
        with open(QUOTAS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_quotas(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUOTAS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_user_usage(username: str) -> dict:
    home_dir = f"/home/{username}"
    if not utils.is_linux():
        return {"disk_used_bytes": 0, "disk_used_human": "0 B", "inode_count": 0}
    result = utils.run_command(
        ["du", "-sb", home_dir],
        check=False,
    )
    disk_bytes = 0
    if result and result.returncode == 0:
        parts = result.stdout.strip().split()
        if parts:
            disk_bytes = int(parts[0])
    # Get inode count
    inodes = 0
    result2 = utils.run_command(
        ["find", home_dir, "-type", "f"],
        check=False,
    )
    if result2 and result2.returncode == 0:
        inodes = len(result2.stdout.strip().splitlines())
    # Convert to human readable
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if disk_bytes < 1024:
            disk_human = f"{disk_bytes:.1f} {unit}"
            break
        disk_bytes /= 1024
    else:
        disk_human = f"{disk_bytes:.1f} PB"
    return {"disk_used_bytes": int(disk_bytes * 1024 ** (["B", "KB", "MB", "GB", "TB"].index(unit) if disk_bytes < 1024 else 4)), "disk_used_human": disk_human, "inode_count": inodes}


class QuotaSet(BaseModel):
    disk_limit_mb: int = 1024
    inode_limit: int = 100000
    bandwidth_limit_gb: Optional[float] = None


@router.get("")
def list_quotas(user: dict = Depends(get_current_user)):
    quotas = _load_quotas()
    result = []
    for username, quota in quotas.items():
        usage = _get_user_usage(username)
        result.append({
            "username": username,
            "disk_limit_mb": quota.get("disk_limit_mb", 1024),
            "inode_limit": quota.get("inode_limit", 100000),
            "bandwidth_limit_gb": quota.get("bandwidth_limit_gb"),
            "current_usage": usage,
        })
    return {"quotas": result}


@router.put("/{username}")
def set_quota(username: str, body: QuotaSet, user: dict = Depends(get_current_user)):
    quotas = _load_quotas()
    quotas[username] = {
        "disk_limit_mb": body.disk_limit_mb,
        "inode_limit": body.inode_limit,
        "bandwidth_limit_gb": body.bandwidth_limit_gb,
    }
    _save_quotas(quotas)
    # Apply system quota if Linux
    if utils.is_linux():
        # Set disk quota using edquota or quota
        home_dir = f"/home/{username}"
        quota_blocks = body.disk_limit_mb * 1024  # KB blocks
        # Try xfs quota
        utils.run_command(
            ["xfs_quota", "-x", "-c", f"limit bsoft={quota_blocks}k bhard={quota_blocks}k {username}", "/"],
            check=False,
        )
    return {"status": "quota set", "username": username, "disk_limit_mb": body.disk_limit_mb}


@router.get("/{username}/usage")
def get_usage(username: str, user: dict = Depends(get_current_user)):
    quotas = _load_quotas()
    if username not in quotas:
        raise HTTPException(status_code=404, detail="No quota set for this user")
    usage = _get_user_usage(username)
    quota = quotas[username]
    return {
        "username": username,
        "quota": quota,
        "usage": usage,
        "percent_used": round((usage.get("disk_used_bytes", 0) / (quota.get("disk_limit_mb", 1024) * 1024 * 1024)) * 100, 1) if quota.get("disk_limit_mb") else 0,
    }
