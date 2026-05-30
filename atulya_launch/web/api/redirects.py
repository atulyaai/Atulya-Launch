"""URL redirect management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/redirects", tags=["redirects"])

REDIRECTS_FILE = utils.CONFIG_DIR / "redirects.json"


def _load_redirects() -> dict:
    if REDIRECTS_FILE.exists():
        import json
        with open(REDIRECTS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_redirects(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    import json
    with open(REDIRECTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _next_id(data: dict) -> int:
    if not data:
        return 1
    return max(int(k) for k in data.keys()) + 1


class RedirectCreate(BaseModel):
    from_url: str
    to_url: str
    redirect_type: int = 302


class RedirectUpdate(BaseModel):
    to_url: Optional[str] = None
    redirect_type: Optional[int] = None


@router.get("")
def list_redirects(user: dict = Depends(get_current_user)):
    data = _load_redirects()
    return {"redirects": data}


@router.post("")
def create_redirect(body: RedirectCreate, user: dict = Depends(get_current_user)):
    if body.redirect_type not in (301, 302, 307):
        raise HTTPException(status_code=400, detail="Redirect type must be 301, 302, or 307")
    data = _load_redirects()
    nid = _next_id(data)
    record = {
        "from_url": body.from_url,
        "to_url": body.to_url,
        "type": body.redirect_type,
        "created_by": user.get("sub", "admin"),
    }
    data[str(nid)] = record
    _save_redirects(data)
    return {"status": "created", "id": str(nid)}


@router.delete("/{redirect_id}")
def delete_redirect(redirect_id: str, user: dict = Depends(get_current_user)):
    data = _load_redirects()
    if redirect_id not in data:
        raise HTTPException(status_code=404, detail="Redirect not found")
    del data[redirect_id]
    _save_redirects(data)
    return {"status": "deleted", "id": redirect_id}


@router.put("/{redirect_id}")
def update_redirect(redirect_id: str, body: RedirectUpdate, user: dict = Depends(get_current_user)):
    data = _load_redirects()
    if redirect_id not in data:
        raise HTTPException(status_code=404, detail="Redirect not found")
    if body.to_url is not None:
        data[redirect_id]["to_url"] = body.to_url
    if body.redirect_type is not None:
        if body.redirect_type not in (301, 302, 307):
            raise HTTPException(status_code=400, detail="Redirect type must be 301, 302, or 307")
        data[redirect_id]["type"] = body.redirect_type
    _save_redirects(data)
    return {"status": "updated", "id": redirect_id, "entry": data[redirect_id]}
