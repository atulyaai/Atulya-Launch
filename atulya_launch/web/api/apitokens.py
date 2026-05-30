"""API token management."""

import json
import secrets
import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/tokens", tags=["tokens"])

TOKENS_FILE = utils.CONFIG_DIR / "api_tokens.json"


def _load_tokens() -> dict:
    if TOKENS_FILE.exists():
        with open(TOKENS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_tokens(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_FILE, "w") as f:
        json.dump(data, f, indent=2)


class TokenCreate(BaseModel):
    name: str
    permissions: List[str] = ["read"]
    expires_days: Optional[int] = 30


@router.get("")
def list_tokens(user: dict = Depends(get_current_user)):
    tokens = _load_tokens()
    username = user.get("sub", "admin")
    result = []
    for tid, token in tokens.items():
        if token.get("created_by") == username:
            # Mask the token value
            masked = token.get("token", "")[:8] + "..." if token.get("token") else ""
            expired = False
            if token.get("expires_at"):
                exp = datetime.datetime.fromisoformat(token["expires_at"])
                expired = exp < datetime.datetime.now(datetime.timezone.utc)
            result.append({
                "id": tid,
                "name": token.get("name", ""),
                "permissions": token.get("permissions", []),
                "token_preview": masked,
                "expires_at": token.get("expires_at"),
                "created_at": token.get("created_at"),
                "expired": expired,
            })
    return {"tokens": result}


@router.post("")
def create_token(body: TokenCreate, user: dict = Depends(get_current_user)):
    tokens = _load_tokens()
    # Generate token
    token_value = secrets.token_hex(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = None
    if body.expires_days:
        expires_at = (now + datetime.timedelta(days=body.expires_days)).isoformat()
    # Find next ID
    tid = str(max((int(k) for k in tokens.keys()), default=0) + 1)
    tokens[tid] = {
        "name": body.name,
        "token": token_value,
        "permissions": body.permissions,
        "created_by": user.get("sub", "admin"),
        "created_at": now.isoformat(),
        "expires_at": expires_at,
    }
    _save_tokens(tokens)
    return {
        "status": "token created",
        "id": tid,
        "token": token_value,
        "name": body.name,
        "expires_at": expires_at,
        "message": "Save this token. It will not be shown again.",
    }


@router.delete("/{token_id}")
def revoke_token(token_id: str, user: dict = Depends(get_current_user)):
    tokens = _load_tokens()
    if token_id not in tokens:
        raise HTTPException(status_code=404, detail="Token not found")
    username = user.get("sub", "admin")
    if tokens[token_id].get("created_by") != username:
        raise HTTPException(status_code=403, detail="Not your token")
    del tokens[token_id]
    _save_tokens(tokens)
    return {"status": "revoked", "id": token_id}
