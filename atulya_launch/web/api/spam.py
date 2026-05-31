"""Spam filtering (SpamAssassin) API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/spam", tags=["spam"])


class SpamRuleCreate(BaseModel):
    rule: str
    action: str = "reject"
    description: Optional[str] = None


def _load_spam_config() -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM spam_config").fetchall()
    config = {}
    for r in rows:
        try:
            config[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            config[r["key"]] = r["value"]
    return config


def _save_spam_config(data: dict):
    with connect() as conn:
        for key, value in data.items():
            conn.execute(
                "INSERT OR REPLACE INTO spam_config (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )


@router.get("/status")
def spam_status(user: dict = Depends(get_current_user)):
    config = _load_spam_config()
    sa_installed = False
    if utils.is_linux():
        result = utils.run_command(["which", "spamassassin"], check=False)
        sa_installed = result and result.returncode == 0
    return {"enabled": config.get("enabled", False), "spamassassin_installed": sa_installed}


@router.post("/enable")
def enable_spam(user: dict = Depends(get_current_user)):
    _save_spam_config({"enabled": True})
    if utils.is_linux():
        utils.run_command(["systemctl", "start", "spamassassin"], check=False)
        utils.run_command(["systemctl", "enable", "spamassassin"], check=False)
    return {"status": "enabled"}


@router.post("/disable")
def disable_spam(user: dict = Depends(get_current_user)):
    _save_spam_config({"enabled": False})
    if utils.is_linux():
        utils.run_command(["systemctl", "stop", "spamassassin"], check=False)
        utils.run_command(["systemctl", "disable", "spamassassin"], check=False)
    return {"status": "disabled"}


@router.get("/rules")
def list_rules(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT id, rule, action, description FROM spam_rules").fetchall()
    return {"rules": [dict(r) for r in rows]}


@router.post("/rules")
def add_rule(body: SpamRuleCreate, user: dict = Depends(get_current_user)):
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO spam_rules (rule, action, description) VALUES (?, ?, ?)",
            (body.rule, body.action, body.description or ""),
        )
        rule_id = cursor.lastrowid
    if utils.is_linux():
        conf = f"header {body.rule} {body.rule}\n score {body.rule} 10.0\ndescribe {body.rule} {body.description or body.rule}\n"
        utils.run_command(["bash", "-c", f"echo '{conf}' >> /etc/spamassassin/local.cf"], check=False)
        utils.run_command(["systemctl", "restart", "spamassassin"], check=False)
    return {"status": "created", "rule": {"id": rule_id, "rule": body.rule, "action": body.action, "description": body.description or ""}}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM spam_rules WHERE id = ?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")
        conn.execute("DELETE FROM spam_rules WHERE id = ?", (rule_id,))
    return {"status": "deleted", "id": rule_id}
