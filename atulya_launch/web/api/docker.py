"""Docker container management API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/docker", tags=["docker"])


def _docker_available():
    result = utils.run_command(["which", "docker"], check=False)
    return result and result.returncode == 0


@router.get("/containers")
def list_containers(user: dict = Depends(get_current_user)):
    if not _docker_available():
        return {"containers": [], "note": "Docker not installed"}
    result = utils.run_command(
        ["docker", "ps", "-a", "--format", '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","ports":"{{.Ports}}","state":"{{.State}}"}'],
        check=False,
    )
    containers = []
    if result and result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return {"containers": containers}


@router.post("/containers/{container_id}/start")
def start_container(container_id: str, user: dict = Depends(get_current_user)):
    if not _docker_available():
        raise HTTPException(status_code=500, detail="Docker not installed")
    result = utils.run_command(["docker", "start", container_id], check=False)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to start container")
    return {"status": "started", "id": container_id}


@router.post("/containers/{container_id}/stop")
def stop_container(container_id: str, user: dict = Depends(get_current_user)):
    if not _docker_available():
        raise HTTPException(status_code=500, detail="Docker not installed")
    result = utils.run_command(["docker", "stop", container_id], check=False)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to stop container")
    return {"status": "stopped", "id": container_id}


@router.post("/containers/{container_id}/restart")
def restart_container(container_id: str, user: dict = Depends(get_current_user)):
    if not _docker_available():
        raise HTTPException(status_code=500, detail="Docker not installed")
    result = utils.run_command(["docker", "restart", container_id], check=False)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to restart container")
    return {"status": "restarted", "id": container_id}


@router.delete("/containers/{container_id}")
def remove_container(container_id: str, user: dict = Depends(get_current_user)):
    if not _docker_available():
        raise HTTPException(status_code=500, detail="Docker not installed")
    result = utils.run_command(["docker", "rm", "-f", container_id], check=False)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to remove container")
    return {"status": "removed", "id": container_id}


@router.get("/containers/{container_id}/logs")
def container_logs(container_id: str, lines: int = 100, user: dict = Depends(get_current_user)):
    if not _docker_available():
        return {"logs": "Docker not installed"}
    result = utils.run_command(
        ["docker", "logs", "--tail", str(lines), container_id],
        check=False,
    )
    logs = result.stdout if result and result.returncode == 0 else ""
    return {"logs": logs}


@router.get("/images")
def list_images(user: dict = Depends(get_current_user)):
    if not _docker_available():
        return {"images": [], "note": "Docker not installed"}
    result = utils.run_command(
        ["docker", "images", "--format", '{"repository":"{{.Repository}}","tag":"{{.Tag}}","size":"{{.Size}}","created":"{{.CreatedSince}}"}'],
        check=False,
    )
    images = []
    if result and result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    images.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return {"images": images}


@router.post("/pull")
def pull_image(body: dict, user: dict = Depends(get_current_user)):
    image = body.get("image", "")
    if not image:
        raise HTTPException(status_code=400, detail="Image name required")
    if not _docker_available():
        raise HTTPException(status_code=500, detail="Docker not installed")
    result = utils.run_command(["docker", "pull", image], check=False, timeout=300)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to pull image")
    return {"status": "pulling", "image": image}


@router.get("/compose")
def list_compose_projects(user: dict = Depends(get_current_user)):
    if not _docker_available():
        return {"projects": [], "note": "Docker not installed"}
    result = utils.run_command(
        ["docker", "compose", "ls", "--format", "json"],
        check=False,
    )
    projects = []
    if result and result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    projects.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return {"projects": projects}


@router.post("/compose/up")
def compose_up(body: dict, user: dict = Depends(get_current_user)):
    path = body.get("path", ".")
    if not _docker_available():
        raise HTTPException(status_code=500, detail="Docker not installed")
    result = utils.run_command(["docker", "compose", "up", "-d"], check=False, workdir=path, timeout=300)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to start compose")
    return {"status": "started", "path": path}


@router.post("/compose/down")
def compose_down(body: dict, user: dict = Depends(get_current_user)):
    path = body.get("path", ".")
    if not _docker_available():
        raise HTTPException(status_code=500, detail="Docker not installed")
    result = utils.run_command(["docker", "compose", "down"], check=False, workdir=path)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to stop compose")
    return {"status": "stopped", "path": path}
