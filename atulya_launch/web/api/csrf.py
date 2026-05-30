"""CSRF protection token management API."""

import secrets
import time
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/csrf", tags=["csrf"])

CSRF_TOKENS_FILE = utils.CONFIG_DIR / "csrf_tokens.json"
TOKEN_EXPIRY_SECONDS = 3600


def _load_tokens() -> dict:
    if CSRF_TOKENS_FILE.exists():
        with open(CSRF_TOKENS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_tokens(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CSRF_TOKENS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _cleanup_tokens():
    tokens = _load_tokens()
    now = time.time()
    expired = [t for t, data in tokens.items() if now - data.get("created_at", 0) > TOKEN_EXPIRY_SECONDS]
    for t in expired:
        del tokens[t]
    if expired:
        _save_tokens(tokens)


@router.get("/token")
def generate_csrf_token(user: dict = Depends(get_current_user)):
    _cleanup_tokens()

    token = secrets.token_urlsafe(32)
    tokens = _load_tokens()
    tokens[token] = {
        "token": token,
        "user": user.get("sub", "admin"),
        "created_at": time.time(),
        "used": False,
    }
    _save_tokens(tokens)

    return {"token": token, "expires_in": TOKEN_EXPIRY_SECONDS}


@router.post("/validate")
def validate_csrf_token(token: str, user: dict = Depends(get_current_user)):
    _cleanup_tokens()

    tokens = _load_tokens()
    if token not in tokens:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    token_data = tokens[token]

    if time.time() - token_data.get("created_at", 0) > TOKEN_EXPIRY_SECONDS:
        del tokens[token]
        _save_tokens(tokens)
        raise HTTPException(status_code=403, detail="CSRF token expired")

    del tokens[token]
    _save_tokens(tokens)

    return {"valid": True, "user": token_data.get("user")}
