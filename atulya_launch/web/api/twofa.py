"""Two-factor authentication API — backed by the unified SQLite 2FA store."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web import twofa_store

router = APIRouter(prefix="/api/2fa", tags=["2fa"])


def _username(user: dict) -> str:
    return user.get("sub", "admin")


class CodeRequest(BaseModel):
    code: str


@router.get("/status")
def twofa_status(user: dict = Depends(get_current_user)):
    username = _username(user)
    enabled = twofa_store.is_enabled(username)
    pending = bool(twofa_store.get_user_2fa(username))
    return {"enabled": enabled, "pending": pending, "username": username}


@router.post("/enable")
def enable_2fa(user: dict = Depends(get_current_user)):
    username = _username(user)
    record = twofa_store.get_user_2fa(username)
    if record and record.get("enabled"):
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    info = twofa_store.start_setup(username)
    return {
        "secret": info["secret"],
        "qr_code": info["qr_code"],
        "message": "Scan the QR code with your authenticator app, then verify with /api/2fa/verify",
    }


@router.post("/verify")
def verify_2fa(body: CodeRequest, user: dict = Depends(get_current_user)):
    username = _username(user)
    result = twofa_store.enable(username, body.code)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid code"))
    return {"status": result["status"], "backup_codes": result.get("backup_codes", [])}


@router.post("/disable")
def disable_2fa(body: CodeRequest, user: dict = Depends(get_current_user)):
    username = _username(user)
    result = twofa_store.disable(username, body.code)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid code"))
    return {"status": result["status"]}


@router.get("/backup-codes")
def get_backup_codes(user: dict = Depends(get_current_user)):
    username = _username(user)
    result = twofa_store.regenerate_backup_codes(username)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "2FA must be enabled"))
    return {"backup_codes": result["backup_codes"], "message": "Save these codes. They will not be shown again."}