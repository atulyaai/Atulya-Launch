"""Password policy configuration API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/settings/password-policy", tags=["password-policy"])

PASSWORD_POLICY_FILE = utils.CONFIG_DIR / "password_policy.json"

DEFAULT_POLICY = {
    "min_length": 8,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digits": True,
    "require_special": True,
    "special_characters": "!@#$%^&*()_+-=[]{}|;:',.<>?",
    "max_length": 128,
    "expiry_days": 90,
    "history_count": 5,
    "lockout_attempts": 5,
    "lockout_duration_minutes": 30,
}


def _load_policy() -> dict:
    if PASSWORD_POLICY_FILE.exists():
        with open(PASSWORD_POLICY_FILE, "r") as f:
            stored = json.load(f) or {}
            policy = DEFAULT_POLICY.copy()
            policy.update(stored)
            return policy
    return DEFAULT_POLICY.copy()


def _save_policy(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PASSWORD_POLICY_FILE, "w") as f:
        json.dump(data, f, indent=2)


class PasswordPolicyUpdate(BaseModel):
    min_length: Optional[int] = None
    require_uppercase: Optional[bool] = None
    require_lowercase: Optional[bool] = None
    require_digits: Optional[bool] = None
    require_special: Optional[bool] = None
    special_characters: Optional[str] = None
    max_length: Optional[int] = None
    expiry_days: Optional[int] = None
    history_count: Optional[int] = None
    lockout_attempts: Optional[int] = None
    lockout_duration_minutes: Optional[int] = None


def validate_password_strength(password: str, policy: dict = None) -> dict:
    if policy is None:
        policy = _load_policy()

    errors = []
    if len(password) < policy.get("min_length", 8):
        errors.append(f"Password must be at least {policy['min_length']} characters")
    if len(password) > policy.get("max_length", 128):
        errors.append(f"Password must be at most {policy['max_length']} characters")
    if policy.get("require_uppercase") and not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    if policy.get("require_lowercase") and not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    if policy.get("require_digits") and not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")
    if policy.get("require_special"):
        special_chars = policy.get("special_characters", "!@#$%^&*()_+-=[]{}|;:',.<>?")
        if not any(c in special_chars for c in password):
            errors.append("Password must contain at least one special character")

    return {"valid": len(errors) == 0, "errors": errors}


@router.get("")
def get_password_policy(user: dict = Depends(get_current_user)):
    return {"policy": _load_policy()}


@router.put("")
def update_password_policy(body: PasswordPolicyUpdate, user: dict = Depends(get_current_user)):
    policy = _load_policy()

    if body.min_length is not None:
        if body.min_length < 4 or body.min_length > 128:
            raise HTTPException(status_code=400, detail="min_length must be between 4 and 128")
        policy["min_length"] = body.min_length
    if body.require_uppercase is not None:
        policy["require_uppercase"] = body.require_uppercase
    if body.require_lowercase is not None:
        policy["require_lowercase"] = body.require_lowercase
    if body.require_digits is not None:
        policy["require_digits"] = body.require_digits
    if body.require_special is not None:
        policy["require_special"] = body.require_special
    if body.special_characters is not None:
        policy["special_characters"] = body.special_characters
    if body.max_length is not None:
        policy["max_length"] = body.max_length
    if body.expiry_days is not None:
        if body.expiry_days < 0:
            raise HTTPException(status_code=400, detail="expiry_days must be non-negative")
        policy["expiry_days"] = body.expiry_days
    if body.history_count is not None:
        if body.history_count < 0 or body.history_count > 50:
            raise HTTPException(status_code=400, detail="history_count must be between 0 and 50")
        policy["history_count"] = body.history_count
    if body.lockout_attempts is not None:
        policy["lockout_attempts"] = body.lockout_attempts
    if body.lockout_duration_minutes is not None:
        policy["lockout_duration_minutes"] = body.lockout_duration_minutes

    _save_policy(policy)
    return {"status": "updated", "policy": policy}
