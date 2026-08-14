"""In-browser SSH terminal API — asyncssh backend with WebSocket pty."""

import asyncio
import datetime
import uuid
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(tags=["ssh-terminal"])

SESSIONS_FILE = utils.CONFIG_DIR / "ssh_sessions.json"

_active_connections: dict[str, any] = {}


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
        return json.loads(SESSIONS_FILE.read_text())
    return {"sessions": {}}


def _save_sessions(data: dict):
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS_FILE.write_text(json.dumps(data, indent=2))


def _has_asyncssh() -> bool:
    try:
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
        "password": body.password,
        "key_path": body.key_path,
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
    if not _has_asyncssh():
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
        import asyncssh
        loop = asyncio.new_event_loop()
        try:
            async def _run():
                conn = await asyncssh.connect(
                    session["host"],
                    port=session.get("port", 22),
                    username=session["username"],
                    password=session.get("password"),
                    client_keys=[session["key_path"]] if session.get("key_path") else None,
                    known_hosts=None,
                )
                result = await conn.run(body.command, timeout=60)
                conn.close()
                return result.stdout, result.stderr, result.exit_status
            stdout, stderr, exit_code = loop.run_until_complete(_run())
            return {
                "session_id": body.session_id,
                "command": body.command,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": exit_code,
            }
        finally:
            loop.close()
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
    conn = _active_connections.pop(session_id, None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
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

    if _has_asyncssh():
        await _handle_asyncssh_websocket(websocket, session_id, session)
    else:
        await _handle_fallback_websocket(websocket, session)


async def _handle_asyncssh_websocket(websocket: WebSocket, session_id: str, session: dict):
    """Handle SSH WebSocket with asyncssh for proper pty support."""
    try:
        import asyncssh
    except ImportError:
        await websocket.send_json({"error": "asyncssh not installed"})
        await websocket.close()
        return

    conn = None
    chan = None
    try:
        conn = await asyncssh.connect(
            session["host"],
            port=session.get("port", 22),
            username=session["username"],
            password=session.get("password"),
            client_keys=[session["key_path"]] if session.get("key_path") else None,
            known_hosts=None,
        )
        _active_connections[session_id] = conn

        chan, _, _ = await conn.open_session(term_type="xterm-256color", term_size=(24, 80))
        await websocket.send_json({"status": "connected", "session_id": session_id})

        async def read_from_ssh():
            try:
                while True:
                    data = await chan.read(65536)
                    if not data:
                        break
                    await websocket.send_text(data)
            except Exception:
                pass

        reader_task = asyncio.create_task(read_from_ssh())

        try:
            while True:
                msg = await websocket.receive_text()
                try:
                    cmd = json.loads(msg)
                    if cmd.get("type") == "resize":
                        await chan.resize(cmd.get("rows", 24), cmd.get("cols", 80))
                    elif cmd.get("type") == "input":
                        chan.write(cmd.get("data", ""))
                except (json.JSONDecodeError, ValueError):
                    chan.write(msg)
        except WebSocketDisconnect:
            pass
        finally:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        if chan:
            try:
                chan.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        _active_connections.pop(session_id, None)
        try:
            await websocket.close()
        except Exception:
            pass


async def _handle_fallback_websocket(websocket: WebSocket, session: dict):
    """Fallback: local shell exec per command (no interactive pty)."""
    import subprocess
    try:
        while True:
            msg = await websocket.receive_text()
            if msg.strip() == "exit":
                break
            try:
                result = subprocess.run(
                    msg, shell=True, capture_output=True, text=True, timeout=60
                )
                output = result.stdout or result.stderr
                await websocket.send_text(output)
            except subprocess.TimeoutExpired:
                await websocket.send_text("ERROR: Command timed out after 60s\n")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
