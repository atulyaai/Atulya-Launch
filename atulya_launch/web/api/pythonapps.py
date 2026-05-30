"""Python app management API (gunicorn + systemd)."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/pythonapps", tags=["pythonapps"])


class PythonAppCreate(BaseModel):
    name: str
    repo_path: str
    port: Optional[int] = 8000
    python_version: Optional[str] = None
    wsgi_app: str = "app:app"


def _pythonapps_file():
    return utils.CONFIG_DIR / "pythonapps.json"


def _load_apps() -> dict:
    p = _pythonapps_file()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _save_apps(data: dict):
    p = _pythonapps_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _systemd_unit(name: str, repo_path: str, port: int, wsgi_app: str) -> str:
    return f"""[Unit]
Description={name} Python App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={repo_path}
ExecStart=/usr/bin/gunicorn --bind 0.0.0.0:{port} {wsgi_app}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


@router.get("")
def list_apps(user: dict = Depends(get_current_user)):
    data = _load_apps()
    if utils.is_linux():
        for app_name, app_data in data.items():
            result = utils.run_command(["systemctl", "is-active", f"{app_name}.service"], check=False)
            app_data["status"] = "running" if result and result.returncode == 0 else "stopped"
    return {"apps": data}


@router.post("")
def create_app(body: PythonAppCreate, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if body.name in data:
        raise HTTPException(status_code=409, detail="App already exists")
    data[body.name] = {
        "name": body.name,
        "repo_path": body.repo_path,
        "port": body.port,
        "python_version": body.python_version,
        "wsgi_app": body.wsgi_app,
        "status": "stopped",
        "created_at": __import__("datetime").datetime.now().isoformat(),
    }
    _save_apps(data)
    if utils.is_linux():
        unit = _systemd_unit(body.name, body.repo_path, body.port or 8000, body.wsgi_app)
        unit_path = f"/etc/systemd/system/{body.name}.service"
        utils.run_command(["bash", "-c", f"cat > {unit_path} << 'EOF'\n{unit}EOF"], check=False)
        utils.run_command(["systemctl", "daemon-reload"], check=False)
    return {"status": "created", "name": body.name}


@router.delete("/{name}")
def delete_app(name: str, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if name not in data:
        raise HTTPException(status_code=404, detail="App not found")
    if utils.is_linux():
        utils.run_command(["systemctl", "stop", f"{name}.service"], check=False)
        utils.run_command(["rm", "-f", f"/etc/systemd/system/{name}.service"], check=False)
        utils.run_command(["systemctl", "daemon-reload"], check=False)
    del data[name]
    _save_apps(data)
    return {"status": "deleted", "name": name}


@router.post("/{name}/start")
def start_app(name: str, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if name not in data:
        raise HTTPException(status_code=404, detail="App not found")
    if utils.is_linux():
        result = utils.run_command(["systemctl", "start", f"{name}.service"], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail="Failed to start app")
        utils.run_command(["systemctl", "enable", f"{name}.service"], check=False)
    data[name]["status"] = "running"
    _save_apps(data)
    return {"status": "started", "name": name}


@router.post("/{name}/stop")
def stop_app(name: str, user: dict = Depends(get_current_user)):
    data = _load_apps()
    if name not in data:
        raise HTTPException(status_code=404, detail="App not found")
    if utils.is_linux():
        result = utils.run_command(["systemctl", "stop", f"{name}.service"], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail="Failed to stop app")
    data[name]["status"] = "stopped"
    _save_apps(data)
    return {"status": "stopped", "name": name}


@router.get("/{name}/logs")
def app_logs(name: str, lines: int = 100, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        return {"logs": "Logs only available on Linux"}
    result = utils.run_command(["journalctl", "-u", f"{name}.service", "-n", str(lines), "--no-pager"], check=False)
    logs = result.stdout if result and result.returncode == 0 else ""
    return {"logs": logs}
