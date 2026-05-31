"""Git deployment API."""

import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/git", tags=["git"])

GIT_REPOS_FILE = utils.CONFIG_DIR / "git_repos.json"


def _load_repos() -> dict:
    if GIT_REPOS_FILE.exists():
        with open(GIT_REPOS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_repos(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(GIT_REPOS_FILE, "w") as f:
        json.dump(data, f, indent=2)


class CloneRequest(BaseModel):
    url: str
    target_path: str
    branch: str = "main"


class PullRequest(BaseModel):
    repo_id: str


class WebhookRequest(BaseModel):
    repo_id: str
    branch: str = "main"
    secret: Optional[str] = None


@router.get("/repos")
def list_repos(user: dict = Depends(get_current_user)):
    repos = _load_repos()
    result = []
    for rid, repo in repos.items():
        repo_dir = repo.get("path", "")
        status = "cloned" if os.path.isdir(repo_dir) else "missing"
        # Check for updates
        if utils.is_linux() and os.path.isdir(repo_dir):
            r = utils.run_command(
                ["git", "-C", repo_dir, "status", "--porcelain"],
                check=False,
            )
            if r and r.returncode == 0:
                status = "clean" if not r.stdout.strip() else "dirty"
        result.append({"id": rid, "status": status, **repo})
    return {"repos": result}


@router.post("/clone")
def clone_repo(body: CloneRequest, user: dict = Depends(get_current_user)):
    if os.path.exists(body.target_path):
        raise HTTPException(status_code=400, detail="Target path already exists")
    result = utils.run_command(
        ["git", "clone", "-b", body.branch, body.url, body.target_path],
        check=False,
        timeout=120,
    )
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Clone failed: {result.stderr or 'unknown error'}")
    repos = _load_repos()
    repo_id = os.path.basename(body.target_path).replace(".git", "")
    repos[repo_id] = {
        "url": body.url,
        "path": body.target_path,
        "branch": body.branch,
        "cloned_by": user.get("sub", "admin"),
    }
    _save_repos(repos)
    return {"status": "cloned", "repo_id": repo_id, "path": body.target_path}


@router.post("/pull")
def pull_repo(body: PullRequest, user: dict = Depends(get_current_user)):
    repos = _load_repos()
    if body.repo_id not in repos:
        raise HTTPException(status_code=404, detail="Repository not found")
    repo = repos[body.repo_id]
    repo_path = repo.get("path", "")
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail="Repository directory not found")
    branch = repo.get("branch", "main")
    result = utils.run_command(
        ["git", "-C", repo_path, "pull", "origin", branch],
        check=False,
        timeout=120,
    )
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Pull failed: {result.stderr or 'unknown error'}")
    output = result.stdout.strip() if result else ""
    return {"status": "pulled", "repo_id": body.repo_id, "output": output}


@router.get("/log/{repo_id}")
def get_commit_log(repo_id: str, user: dict = Depends(get_current_user)):
    repos = _load_repos()
    if repo_id not in repos:
        raise HTTPException(status_code=404, detail="Repository not found")
    repo_path = repos[repo_id].get("path", "")
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail="Repository directory not found")
    result = utils.run_command(
        ["git", "-C", repo_path, "log", "--oneline", "-20"],
        check=False,
    )
    commits = []
    if result and result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append({"hash": parts[0], "message": parts[1]})
    return {"repo_id": repo_id, "commits": commits}


@router.post("/webhook")
def setup_webhook(body: WebhookRequest, user: dict = Depends(get_current_user)):
    repos = _load_repos()
    if body.repo_id not in repos:
        raise HTTPException(status_code=404, detail="Repository not found")
    secret = body.secret or utils.generate_password(32)
    repos[body.repo_id]["webhook_secret"] = secret
    repos[body.repo_id]["webhook_branch"] = body.branch
    _save_repos(repos)
    # Create webhook script
    script_dir = str(utils.CONFIG_DIR / "webhooks")
    os.makedirs(script_dir, exist_ok=True)
    script_path = os.path.join(script_dir, f"{body.repo_id}.sh")
    repo_path = repos[body.repo_id].get("path", "")
    branch = body.branch
    script_content = f"""#!/bin/bash
# Auto-deploy webhook for {body.repo_id}
cd "{repo_path}"
git pull origin {branch}
"""
    with open(script_path, "w") as f:
        f.write(script_content)
    if utils.is_linux():
        os.chmod(script_path, 0o755)
    webhook_url = f"/api/webhook/deploy/{body.repo_id}?secret={secret}"
    return {
        "status": "webhook configured",
        "repo_id": body.repo_id,
        "webhook_url": webhook_url,
        "secret": secret,
        "branch": body.branch,
    }
