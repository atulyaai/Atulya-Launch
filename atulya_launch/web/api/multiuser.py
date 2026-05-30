"""Multi-user / RBAC management API."""

import datetime
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user, _hash_password, _verify_password

router = APIRouter(prefix="/api/users", tags=["users-rbac"])

USERS_FILE = utils.CONFIG_DIR / "panel_users.json"

VALID_ROLES = {"admin", "editor", "viewer"}
ROLE_PERMISSIONS = {
    "admin": ["read", "write", "delete", "manage_users", "manage_settings"],
    "editor": ["read", "write"],
    "viewer": ["read"],
}


class PanelUserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "viewer"


class RoleUpdate(BaseModel):
    role: str


class PasswordUpdate(BaseModel):
    new_password: str


def _load_users() -> dict:
    if USERS_FILE.exists():
        import json
        return json.loads(USERS_FILE.read_text())
    return {"users": {}}


def _save_users(data: dict):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    USERS_FILE.write_text(json.dumps(data, indent=2))


@router.get("")
def list_users(user: dict = Depends(get_current_user)):
    data = _load_users()
    safe_users = {}
    for uid, u in data.get("users", {}).items():
        safe = {**u}
        safe.pop("password_hash", None)
        safe_users[uid] = safe
    return {"users": safe_users}


@router.post("")
def create_user(body: PanelUserCreate, user: dict = Depends(get_current_user)):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    data = _load_users()
    for uid, u in data.get("users", {}).items():
        if u.get("username") == body.username:
            raise HTTPException(status_code=409, detail="Username already exists")
    user_id = str(uuid.uuid4())[:8]
    data.setdefault("users", {})[user_id] = {
        "id": user_id,
        "username": body.username,
        "password_hash": _hash_password(body.password),
        "email": body.email or "",
        "role": body.role,
        "permissions": ROLE_PERMISSIONS.get(body.role, []),
        "enabled": True,
        "created_at": datetime.datetime.now().isoformat(),
        "created_by": user.get("sub", "admin"),
    }
    _save_users(data)
    return {"status": "created", "user_id": user_id, "username": body.username, "role": body.role}


@router.put("/{user_id}/role")
def update_role(user_id: str, body: RoleUpdate, user: dict = Depends(get_current_user)):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    data = _load_users()
    users = data.get("users", {})
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    users[user_id]["role"] = body.role
    users[user_id]["permissions"] = ROLE_PERMISSIONS.get(body.role, [])
    users[user_id]["updated_at"] = datetime.datetime.now().isoformat()
    _save_users(data)
    return {"status": "updated", "user_id": user_id, "role": body.role}


@router.put("/{user_id}/password")
def update_password(user_id: str, body: PasswordUpdate, user: dict = Depends(get_current_user)):
    data = _load_users()
    users = data.get("users", {})
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    users[user_id]["password_hash"] = _hash_password(body.new_password)
    users[user_id]["updated_at"] = datetime.datetime.now().isoformat()
    _save_users(data)
    return {"status": "password updated", "user_id": user_id}


@router.put("/{user_id}/enable")
def enable_user(user_id: str, user: dict = Depends(get_current_user)):
    data = _load_users()
    users = data.get("users", {})
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    users[user_id]["enabled"] = True
    _save_users(data)
    return {"status": "enabled", "user_id": user_id}


@router.put("/{user_id}/disable")
def disable_user(user_id: str, user: dict = Depends(get_current_user)):
    data = _load_users()
    users = data.get("users", {})
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    users[user_id]["enabled"] = False
    _save_users(data)
    return {"status": "disabled", "user_id": user_id}


@router.delete("/{user_id}")
def delete_user(user_id: str, user: dict = Depends(get_current_user)):
    data = _load_users()
    users = data.get("users", {})
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    if users[user_id].get("username") == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete the admin user")
    del users[user_id]
    _save_users(data)
    return {"status": "deleted", "user_id": user_id}


@router.get("/roles")
def list_roles(user: dict = Depends(get_current_user)):
    return {
        "roles": {
            role: {"permissions": perms}
            for role, perms in ROLE_PERMISSIONS.items()
        }
    }
