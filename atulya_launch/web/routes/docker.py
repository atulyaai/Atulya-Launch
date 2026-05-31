from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ...docker import (
    DOCKER_APPS, docker_available, docker_list_containers,
    docker_list_images, docker_run, docker_stop, docker_start, docker_remove,
)
from ..auth import require_auth
from ..database import audit_log

router = APIRouter(prefix="/docker")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def docker_page(request: Request):
    avail = DOCKER_APPS
    if docker_available():
        containers = docker_list_containers(all_containers=True)
        images = docker_list_images()
    else:
        containers = []
        images = []
    return templates.TemplateResponse(request, "docker.html", {
        "user": request.state.user,
        "available": avail,
        "containers": containers,
        "images": images,
        "docker_available": docker_available(),
    })


@router.post("/run")
@require_auth
async def container_run(request: Request, name: str = Form(...), image: str = Form(...)):
    app_config = DOCKER_APPS.get(image, {})
    result = docker_run(
        name, image,
        ports=app_config.get("ports"),
        env=app_config.get("env"),
        volumes=app_config.get("volumes"),
    )
    audit_log(request.state.user["username"], "docker.run", "ok" if result.get("ok") else "error", {"name": name, "image": image})
    return RedirectResponse("/docker", status_code=302)


@router.post("/stop")
@require_auth
async def container_stop(request: Request, name: str = Form(...)):
    result = docker_stop(name)
    audit_log(request.state.user["username"], "docker.stop", "ok" if result.get("ok") else "error", {"name": name})
    return RedirectResponse("/docker", status_code=302)


@router.post("/start")
@require_auth
async def container_start(request: Request, name: str = Form(...)):
    result = docker_start(name)
    audit_log(request.state.user["username"], "docker.start", "ok" if result.get("ok") else "error", {"name": name})
    return RedirectResponse("/docker", status_code=302)


@router.post("/remove")
@require_auth
async def container_remove(request: Request, name: str = Form(...)):
    result = docker_remove(name, force=True)
    audit_log(request.state.user["username"], "docker.remove", "ok" if result.get("ok") else "error", {"name": name})
    return RedirectResponse("/docker", status_code=302)


@router.get("/api/containers")
@require_auth
async def api_containers(request: Request):
    if not docker_available():
        return JSONResponse({"error": "Docker not available"}, status_code=503)
    return JSONResponse(docker_list_containers(all_containers=True))


@router.get("/api/images")
@require_auth
async def api_images(request: Request):
    if not docker_available():
        return JSONResponse({"error": "Docker not available"}, status_code=503)
    return JSONResponse(docker_list_images())
