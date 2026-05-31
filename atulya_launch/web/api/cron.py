"""Cron job management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/cron", tags=["cron"])


class CronJobCreate(BaseModel):
    schedule: str
    command: str
    comment: Optional[str] = None


class CronJobUpdate(BaseModel):
    schedule: Optional[str] = None
    command: Optional[str] = None
    comment: Optional[str] = None


def _get_crontab() -> str:
    result = utils.run_command(["crontab", "-l"], check=False)
    if result and result.returncode == 0:
        return result.stdout
    return ""


def _set_crontab(content: str):
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cron", delete=False) as f:
        f.write(content)
        tmp = f.name
    try:
        utils.run_command(["crontab", tmp], check=False)
    finally:
        os.unlink(tmp)


def _parse_cron_jobs() -> list:
    raw = _get_crontab()
    jobs = []
    idx = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("SHELL") or line.startswith("PATH") or line.startswith("MAILTO"):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        idx += 1
        jobs.append({
            "id": idx,
            "schedule": f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[4]}",
            "command": parts[5],
            "enabled": True,
        })
    return jobs


@router.get("/jobs")
def list_jobs(user: dict = Depends(get_current_user)):
    return {"jobs": _parse_cron_jobs()}


@router.post("/jobs")
def add_job(body: CronJobCreate, user: dict = Depends(get_current_user)):
    comment_line = f"# {body.comment}\n" if body.comment else ""
    new_line = f"{comment_line}{body.schedule} {body.command}\n"
    current = _get_crontab()
    _set_crontab(current.rstrip() + "\n" + new_line)
    return {"status": "added", "schedule": body.schedule, "command": body.command}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, user: dict = Depends(get_current_user)):
    raw = _get_crontab()
    lines = raw.splitlines()
    idx = 0
    new_lines = []
    skip_next = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if skip_next:
                skip_next = False
                continue
            new_lines.append(line)
            continue
        if not stripped or stripped.startswith("SHELL") or stripped.startswith("PATH") or stripped.startswith("MAILTO"):
            new_lines.append(line)
            continue
        idx += 1
        if idx == job_id:
            skip_next = True
            # Also remove preceding comment line if present
            if new_lines and new_lines[-1].strip().startswith("#"):
                new_lines.pop()
            continue
        new_lines.append(line)
    _set_crontab("\n".join(new_lines) + "\n")
    return {"status": "deleted", "id": job_id}


@router.put("/jobs/{job_id}")
def update_job(job_id: int, body: CronJobUpdate, user: dict = Depends(get_current_user)):
    delete_job(job_id, user)
    schedule = body.schedule or "0 * * * *"
    command = body.command or "echo 'no command'"
    add_body = CronJobCreate(schedule=schedule, command=command, comment=body.comment)
    return add_job(add_body, user)


@router.put("/jobs/{job_id}/enable")
def enable_job(job_id: int, user: dict = Depends(get_current_user)):
    return {"status": "enabled", "id": job_id, "note": "Jobs are enabled by default in crontab"}


@router.put("/jobs/{job_id}/disable")
def disable_job(job_id: int, user: dict = Depends(get_current_user)):
    raw = _get_crontab()
    lines = raw.splitlines()
    idx = 0
    new_lines = []
    skip_next = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if skip_next:
                skip_next = False
                new_lines.append(line)
                continue
            new_lines.append(line)
            continue
        if not stripped or stripped.startswith("SHELL") or stripped.startswith("PATH") or stripped.startswith("MAILTO"):
            new_lines.append(line)
            continue
        idx += 1
        if idx == job_id:
            new_lines.append("# " + line)
            continue
        new_lines.append(line)
    _set_crontab("\n".join(new_lines) + "\n")
    return {"status": "disabled", "id": job_id}
