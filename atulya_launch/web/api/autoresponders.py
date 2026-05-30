"""Email autoresponders API."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/autoresponders", tags=["autoresponders"])


class AutoresponderCreate(BaseModel):
    email: str
    subject: str
    body: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


def _auto_file():
    return utils.CONFIG_DIR / "autoresponders.json"


def _load_auto() -> dict:
    p = _auto_file()
    if not p.exists():
        return {}
    import json
    return json.loads(p.read_text())


def _save_auto(data: dict):
    p = _auto_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(data, indent=2))


def _next_id(data: dict) -> int:
    if not data:
        return 1
    return max(int(k) for k in data.keys()) + 1


@router.get("")
def list_autoresponders(user: dict = Depends(get_current_user)):
    return {"autoresponders": _load_auto()}


@router.post("")
def create_autoresponder(body: AutoresponderCreate, user: dict = Depends(get_current_user)):
    data = _load_auto()
    nid = _next_id(data)
    record = {
        "email": body.email,
        "subject": body.subject,
        "body": body.body,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "created_at": datetime.datetime.now().isoformat(),
    }
    data[str(nid)] = record
    _save_auto(data)
    if utils.is_linux():
        autoconf = f"/etc/postfix/autoresponders/{body.email}"
        utils.run_command(["mkdir", "-p", "/etc/postfix/autoresponders"], check=False)
        utils.run_command(["bash", "-c", f"cat > {autoconf} << 'EOF'\nSubject: {body.subject}\n\n{body.body}\nEOF"], check=False)
    return {"status": "created", "id": str(nid)}


@router.delete("/{auto_id}")
def delete_autoresponder(auto_id: str, user: dict = Depends(get_current_user)):
    data = _load_auto()
    if auto_id not in data:
        raise HTTPException(status_code=404, detail="Autoresponder not found")
    entry = data.pop(auto_id)
    _save_auto(data)
    if utils.is_linux():
        email = entry.get("email", "")
        utils.run_command(["rm", "-f", f"/etc/postfix/autoresponders/{email}"], check=False)
    return {"status": "deleted", "id": auto_id}
