"""In-browser SSH terminal API — session management and WebSocket."""

import asyncio
import datetime
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(tags=["ssh-terminal"])

SESSIONS_FILE = utils.CONFIG_DIR / "ssh_sessions.json"


class SSHConnectRequest(BaseModel):
    host: str = "127.0.0.1"
    port: int = 22
    username: str = "root"
    password: Optional[str] = None
    key_path: Optional[str] = None


class SSHExecRequest(BaseModel):
    session_id: str
    command: str


def _load_sessions() -> dict:
    if SESSIONS_FILE.exists():
        import json
        return json.loads(SESSIONS_FILE.read_text())
    return {"sessions": {}}


def _save_sessions(data: dict):
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    SESSIONS_FILE.write_text(json.dumps(data, indent=2))


def _paramiko_available() -> bool:
    try:
        import paramiko
        return True
    except ImportError:
        return False


@router.post("/api/ssh/connect")
def ssh_connect(body: SSHConnectRequest, user: dict = Depends(get_current_user)):
    session_id = str(uuid.uuid4())[:12]
    data = _load_sessions()
    data.setdefault("sessions", {})[session_id] = {
        "session_id": session_id,
        "host": body.host,
        "port": body.port,
        "username": body.username,
        "status": "connected",
        "created_at": datetime.datetime.now().isoformat(),
        "user": user.get("sub", "admin"),
    }
    _save_sessions(data)
    return {"session_id": session_id, "host": body.host, "status": "connected"}


@router.post("/api/ssh/exec")
def ssh_exec(body: SSHExecRequest, user: dict = Depends(get_current_user)):
    data = _load_sessions()
    sessions = data.get("sessions", {})
    if body.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[body.session_id]
    if not _paramiko_available():
        import subprocess
        try:
            result = subprocess.run(
                body.command, shell=True, capture_output=True, text=True, timeout=60
            )
            return {
                "session_id": body.session_id,
                "command": body.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Command timed out")
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": session["host"],
            "port": session.get("port", 22),
            "username": session["username"],
            "timeout": 10,
        }
        if session.get("key_path"):
            connect_kwargs["key_filename"] = session["key_path"]
        client.connect(**connect_kwargs)
        _, stdout, stderr = client.exec_command(body.command, timeout=60)
        stdout_str = stdout.read().decode()
        stderr_str = stderr.read().decode()
        client.close()
        return {
            "session_id": body.session_id,
            "command": body.command,
            "stdout": stdout_str,
            "stderr": stderr_str,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSH exec failed: {str(e)}")


@router.get("/api/ssh/sessions")
def list_sessions(user: dict = Depends(get_current_user)):
    data = _load_sessions()
    sessions = data.get("sessions", {})
    filtered = {k: v for k, v in sessions.items() if v.get("user") == user.get("sub", "admin")}
    return {"sessions": filtered}


@router.delete("/api/ssh/sessions/{session_id}")
def close_session(session_id: str, user: dict = Depends(get_current_user)):
    data = _load_sessions()
    sessions = data.get("sessions", {})
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]
    _save_sessions(data)
    return {"status": "closed", "session_id": session_id}


@router.websocket("/ws/ssh")
async def ssh_websocket(websocket: WebSocket):
    await websocket.accept()
    session_id = websocket.query_params.get("session_id", "")
    data = _load_sessions()
    session = data.get("sessions", {}).get(session_id)
    if not session:
        await websocket.send_json({"error": "Invalid session"})
        await websocket.close()
        return
    try:
        while True:
            msg = await websocket.receive_text()
            if msg.strip() == "exit":
                break
            if _paramiko_available():
                import paramiko
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                connect_kwargs = {
                    "hostname": session["host"],
                    "port": session.get("port", 22),
                    "username": session["username"],
                    "timeout": 10,
                }
                if session.get("key_path"):
                    connect_kwargs["key_filename"] = session["key_path"]
                client.connect(**connect_kwargs)
                _, stdout, stderr = client.exec_command(msg, timeout=60)
                output = stdout.read().decode() or stderr.read().decode()
                client.close()
                await websocket.send_text(output)
            else:
                import subprocess
                result = subprocess.run(msg, shell=True, capture_output=True, text=True, timeout=60)
                output = result.stdout or result.stderr
                await websocket.send_text(output)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
