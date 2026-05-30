"""Spam filtering (SpamAssassin) API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/spam", tags=["spam"])


class SpamRuleCreate(BaseModel):
    rule: str
    action: str = "reject"
    description: Optional[str] = None


def _spam_config():
    return utils.CONFIG_DIR / "spam.json"


def _load_spam() -> dict:
    p = _spam_config()
    if not p.exists():
        return {"enabled": False, "rules": []}
    import json
    return json.loads(p.read_text())


def _save_spam(data: dict):
    p = _spam_config()
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(data, indent=2))


@router.get("/status")
def spam_status(user: dict = Depends(get_current_user)):
    data = _load_spam()
    sa_installed = False
    if utils.is_linux():
        result = utils.run_command(["which", "spamassassin"], check=False)
        sa_installed = result and result.returncode == 0
    return {"enabled": data.get("enabled", False), "spamassassin_installed": sa_installed}


@router.post("/enable")
def enable_spam(user: dict = Depends(get_current_user)):
    data = _load_spam()
    data["enabled"] = True
    _save_spam(data)
    if utils.is_linux():
        utils.run_command(["systemctl", "start", "spamassassin"], check=False)
        utils.run_command(["systemctl", "enable", "spamassassin"], check=False)
    return {"status": "enabled"}


@router.post("/disable")
def disable_spam(user: dict = Depends(get_current_user)):
    data = _load_spam()
    data["enabled"] = False
    _save_spam(data)
    if utils.is_linux():
        utils.run_command(["systemctl", "stop", "spamassassin"], check=False)
        utils.run_command(["systemctl", "disable", "spamassassin"], check=False)
    return {"status": "disabled"}


@router.get("/rules")
def list_rules(user: dict = Depends(get_current_user)):
    data = _load_spam()
    return {"rules": data.get("rules", [])}


@router.post("/rules")
def add_rule(body: SpamRuleCreate, user: dict = Depends(get_current_user)):
    data = _load_spam()
    rules = data.setdefault("rules", [])
    rule = {
        "id": len(rules) + 1,
        "rule": body.rule,
        "action": body.action,
        "description": body.description or "",
    }
    rules.append(rule)
    _save_spam(data)
    if utils.is_linux():
        conf = f"header {body.rule} {body.rule}\n score {body.rule} 10.0\ndescribe {body.rule} {body.description or body.rule}\n"
        utils.run_command(["bash", "-c", f"echo '{conf}' >> /etc/spamassassin/local.cf"], check=False)
        utils.run_command(["systemctl", "restart", "spamassassin"], check=False)
    return {"status": "created", "rule": rule}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, user: dict = Depends(get_current_user)):
    data = _load_spam()
    rules = data.get("rules", [])
    data["rules"] = [r for r in rules if r.get("id") != rule_id]
    if len(data["rules"]) == len(rules):
        raise HTTPException(status_code=404, detail="Rule not found")
    _save_spam(data)
    return {"status": "deleted", "id": rule_id}
