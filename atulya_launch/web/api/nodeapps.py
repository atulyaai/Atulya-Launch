"""Node.js app management API (PM2)."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/nodeapps", tags=["nodeapps"])


class NodeAppCreate(BaseModel):
    name: str
    repo_path: str
    port: Optional[int] = None
    node_version: Optional[str] = None


def _nodeapps_file():
    return utils.CONFIG_DIR / "nodeapps.json"


def _load_apps() -> dict:
    p = _nodeapps_file()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save_apps(data: dict):
    p = _nodeapps_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _pm2_available():
    result = utils.run_command(["which", "pm2"], check=False)
    return result and result.returncode == 0


@router.get("")
def list_apps(user: dict = Depends(get_current_user)):
    data = _load_apps()
    if _pm2_available():
        result = utils.run_command(["pm2", "jlist"], check=False)
        if result and result.returncode == 0:
            try:
                processes = json.loads(result.stdout)
                for app_name, app_data in data.items():
                    for proc in processes:
                        if proc.get("name") == app_name:
                            app_data["status"] = proc.get("pm2_env", {}).get("status", "unknown")
                            app_data["pid"] = proc.get("pid")
                            break
            except json.JSONDecodeError:
                pass
    return {"apps": data}


@router.post("")
def create_app(body: NodeAppCreate, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if body.name in data:
        raise HTTPException(status_code=409, detail="App already exists")
    data[body.name] = {
        "name": body.name,
        "repo_path": body.repo_path,
        "port": body.port,
        "node_version": body.node_version,
        "status": "stopped",
        "created_at": __import__("datetime").datetime.now().isoformat(),
    }
    _save_apps(data)
    if body.node_version and utils.is_linux():
        utils.run_command(["bash", "-c", f"nvm install {body.node_version} && nvm use {body.node_version}"], check=False)
    if _pm2_available():
        utils.run_command(["pm2", "start", body.repo_path, "--name", body.name], check=False)
        utils.run_command(["pm2", "save"], check=False)
    return {"status": "created", "name": body.name}


@router.delete("/{name}")
def delete_app(name: str, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if name not in data:
        raise HTTPException(status_code=404, detail="App not found")
    del data[name]
    _save_apps(data)
    if _pm2_available():
        utils.run_command(["pm2", "delete", name], check=False)
        utils.run_command(["pm2", "save"], check=False)
    return {"status": "deleted", "name": name}


@router.post("/{name}/start")
def start_app(name: str, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if name not in data:
        raise HTTPException(status_code=404, detail="App not found")
    if _pm2_available():
        result = utils.run_command(["pm2", "start", name], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail="Failed to start app")
        utils.run_command(["pm2", "save"], check=False)
    data[name]["status"] = "running"
    _save_apps(data)
    return {"status": "started", "name": name}


@router.post("/{name}/stop")
def stop_app(name: str, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if name not in data:
        raise HTTPException(status_code=404, detail="App not found")
    if _pm2_available():
        result = utils.run_command(["pm2", "stop", name], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail="Failed to stop app")
        utils.run_command(["pm2", "save"], check=False)
    data[name]["status"] = "stopped"
    _save_apps(data)
    return {"status": "stopped", "name": name}


@router.get("/{name}/logs")
def app_logs(name: str, lines: int = 100, user: dict = Depends(get_current_user)):
    if not _pm2_available():
        return {"logs": "PM2 not installed"}
    result = utils.run_command(["pm2", "logs", name, "--nostream", "--lines", str(lines)], check=False)
    logs = result.stdout if result and result.returncode == 0 else ""
    return {"logs": logs}
