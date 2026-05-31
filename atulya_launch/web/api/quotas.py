"""Disk quota management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/quotas", tags=["quotas"])


def _get_user_usage(username: str) -> dict:
    home_dir = f"/home/{username}"
    if not utils.is_linux():
        return {"disk_used_bytes": 0, "disk_used_human": "0 B", "inode_count": 0}
    result = utils.run_command(["du", "-sb", home_dir], check=False)
    disk_bytes = 0
    if result and result.returncode == 0:
        parts = result.stdout.strip().split()
        if parts:
            disk_bytes = int(parts[0])
    inodes = 0
    result2 = utils.run_command(["find", home_dir, "-type", "f"], check=False)
    if result2 and result2.returncode == 0:
        inodes = len(result2.stdout.strip().splitlines())
    original = disk_bytes
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if disk_bytes < 1024:
            disk_human = f"{disk_bytes:.1f} {unit}"
            break
        disk_bytes /= 1024
    else:
        disk_human = f"{disk_bytes:.1f} PB"
    return {"disk_used_bytes": original, "disk_used_human": disk_human, "inode_count": inodes}


class QuotaSet(BaseModel):
    disk_limit_mb: int = 1024
    inode_limit: int = 100000
    bandwidth_limit_gb: Optional[float] = None


@router.get("")
def list_quotas(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT username, disk_limit_mb, inode_limit, bandwidth_limit_gb FROM user_quotas",
        ).fetchall()
    result = []
    for r in rows:
        usage = _get_user_usage(r["username"])
        result.append({
            "username": r["username"],
            "disk_limit_mb": r["disk_limit_mb"],
            "inode_limit": r["inode_limit"],
            "bandwidth_limit_gb": r["bandwidth_limit_gb"],
            "current_usage": usage,
        })
    return {"quotas": result}


@router.put("/{username}")
def set_quota(username: str, body: QuotaSet, user: dict = Depends(get_current_user)):
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO user_quotas (username, disk_limit_mb, inode_limit, bandwidth_limit_gb)
               VALUES (?, ?, ?, ?)""",
            (username, body.disk_limit_mb, body.inode_limit, body.bandwidth_limit_gb),
        )
    if utils.is_linux():
        quota_blocks = body.disk_limit_mb * 1024
        utils.run_command(
            ["xfs_quota", "-x", "-c", f"limit bsoft={quota_blocks}k bhard={quota_blocks}k {username}", "/"],
            check=False,
        )
    return {"status": "quota set", "username": username, "disk_limit_mb": body.disk_limit_mb}


@router.get("/{username}/usage")
def get_usage(username: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT disk_limit_mb, inode_limit, bandwidth_limit_gb FROM user_quotas WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No quota set for this user")
    usage = _get_user_usage(username)
    quota = dict(row)
    limit_bytes = quota.get("disk_limit_mb", 1024) * 1024 * 1024
    return {
        "username": username,
        "quota": quota,
        "usage": usage,
        "percent_used": round((usage.get("disk_used_bytes", 0) / limit_bytes) * 100, 1) if limit_bytes else 0,
    }
