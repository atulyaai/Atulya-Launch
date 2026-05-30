"""Mailing list management via Mailman API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/mailinglists", tags=["mailinglists"])


class MailingListCreate(BaseModel):
    name: str
    description: Optional[str] = None
    password: Optional[str] = None
    owner: Optional[str] = None
    display_name: Optional[str] = None


class MemberAdd(BaseModel):
    email: str
    display_name: Optional[str] = None


class MemberRemove(BaseModel):
    email: str


def _mailman_available() -> bool:
    result = utils.run_command(["which", "mailman"], check=False)
    return result is not None and result.returncode == 0


def _mailman_api_call(method: str, endpoint: str, data: dict = None) -> dict:
    import urllib.request
    import urllib.error
    import urllib.parse

    base_url = "http://localhost:8001/3.1"
    url = f"{base_url}{endpoint}"

    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 204:
                return {}
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        raise HTTPException(status_code=e.code, detail=f"Mailman API error: {error_body}")
    except urllib.error.URLError as e:
        raise HTTPException(status_code=503, detail=f"Mailman API unreachable: {e.reason}")


def _mailman_installed() -> bool:
    result = utils.run_command(["mailman", "info"], check=False)
    return result is not None and result.returncode == 0


@router.get("")
def list_mailing_lists(user: dict = Depends(get_current_user)):
    if _mailman_available():
        try:
            lists = _mailman_api_call("GET", "/lists")
            return {"mailing_lists": lists.get("entries", []), "source": "mailman"}
        except HTTPException:
            pass

    config = utils.load_config()
    mailing_lists = config.get("mailing_lists", {})
    return {"mailing_lists": mailing_lists, "source": "config"}


@router.post("")
def create_mailing_list(body: MailingListCreate, user: dict = Depends(get_current_user)):
    list_id = f"{body.name}@localhost"

    if _mailman_available():
        try:
            result = _mailman_api_call("POST", "/lists", {
                "fqdn_listname": list_id,
                "description": body.description or f"Mailing list {body.name}",
                "display_name": body.display_name or body.name.title(),
            })
            result["source"] = "mailman"
            return {"mailing_list": result}
        except HTTPException:
            pass

    config = utils.load_config()
    mailing_lists = config.get("mailing_lists", {})
    if list_id in mailing_lists:
        raise HTTPException(status_code=409, detail="Mailing list already exists")

    list_data = {
        "name": body.name,
        "list_id": list_id,
        "description": body.description or f"Mailing list {body.name}",
        "password": body.password or utils.generate_password(12),
        "owner": body.owner or user.get("sub", "admin"),
        "display_name": body.display_name or body.name.title(),
        "members": [],
        "created_at": __import__("datetime").datetime.now().isoformat(),
    }
    mailing_lists[list_id] = list_data
    config["mailing_lists"] = mailing_lists
    utils.save_config(config)

    if _mailman_available():
        result = utils.run_command(["mailman", "create", list_id], check=False)
        if body.password:
            utils.run_command(["mailman", "password", list_id, body.password], check=False)

    return {"mailing_list": list_data}


@router.delete("/{list_name}")
def delete_mailing_list(list_name: str, user: dict = Depends(get_current_user)):
    list_id = f"{list_name}@localhost"

    if _mailman_available():
        try:
            _mailman_api_call("DELETE", f"/lists/{list_id}")
            return {"status": "deleted", "list": list_id, "source": "mailman"}
        except HTTPException:
            pass

    config = utils.load_config()
    mailing_lists = config.get("mailing_lists", {})
    if list_id not in mailing_lists:
        raise HTTPException(status_code=404, detail="Mailing list not found")

    del mailing_lists[list_id]
    config["mailing_lists"] = mailing_lists
    utils.save_config(config)

    return {"status": "deleted", "list": list_id}


@router.post("/{list_name}/members")
def add_member(list_name: str, body: MemberAdd, user: dict = Depends(get_current_user)):
    list_id = f"{list_name}@localhost"

    if _mailman_available():
        try:
            result = _mailman_api_call("POST", f"/lists/{list_id}/members", {
                "email": body.email,
                "display_name": body.display_name,
            })
            return {"status": "added", "member": result, "source": "mailman"}
        except HTTPException:
            pass

    config = utils.load_config()
    mailing_lists = config.get("mailing_lists", {})
    if list_id not in mailing_lists:
        raise HTTPException(status_code=404, detail="Mailing list not found")

    members = mailing_lists[list_id].get("members", [])
    if body.email in [m.get("email") for m in members]:
        raise HTTPException(status_code=409, detail="Member already exists")

    member = {"email": body.email, "display_name": body.display_name or body.email.split("@")[0]}
    members.append(member)
    mailing_lists[list_id]["members"] = members
    config["mailing_lists"] = mailing_lists
    utils.save_config(config)

    return {"status": "added", "member": member}


@router.delete("/{list_name}/members/{email}")
def remove_member(list_name: str, email: str, user: dict = Depends(get_current_user)):
    list_id = f"{list_name}@localhost"

    if _mailman_available():
        try:
            _mailman_api_call("DELETE", f"/lists/{list_id}/members/{email}")
            return {"status": "removed", "email": email, "source": "mailman"}
        except HTTPException:
            pass

    config = utils.load_config()
    mailing_lists = config.get("mailing_lists", {})
    if list_id not in mailing_lists:
        raise HTTPException(status_code=404, detail="Mailing list not found")

    members = mailing_lists[list_id].get("members", [])
    new_members = [m for m in members if m.get("email") != email]
    if len(new_members) == len(members):
        raise HTTPException(status_code=404, detail="Member not found")

    mailing_lists[list_id]["members"] = new_members
    config["mailing_lists"] = mailing_lists
    utils.save_config(config)

    return {"status": "removed", "email": email}


@router.get("/{list_name}/members")
def list_members(list_name: str, user: dict = Depends(get_current_user)):
    list_id = f"{list_name}@localhost"

    if _mailman_available():
        try:
            result = _mailman_api_call("GET", f"/lists/{list_id}/members")
            return {"members": result.get("entries", []), "source": "mailman"}
        except HTTPException:
            pass

    config = utils.load_config()
    mailing_lists = config.get("mailing_lists", {})
    if list_id not in mailing_lists:
        raise HTTPException(status_code=404, detail="Mailing list not found")

    return {"members": mailing_lists[list_id].get("members", [])}
