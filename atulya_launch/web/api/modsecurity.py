"""ModSecurity WAF management API."""

import json
import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/waf", tags=["waf"])

MODSEC_CONF = "/etc/modsecurity/modsecurity.conf"
MODSEC_RULES_DIR = "/etc/modsecurity/rules"


class CustomRuleCreate(BaseModel):
    rule_name: str
    pattern: str
    action: str = "deny"
    phase: int = 1
    severity: int = 2
    description: Optional[str] = None
    enabled: bool = True


def _load_waf_config() -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM waf_config").fetchall()
    config = {}
    for r in rows:
        try:
            config[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            config[r["key"]] = r["value"]
    return config


def _save_waf_config(data: dict):
    with connect() as conn:
        for key, value in data.items():
            conn.execute(
                "INSERT OR REPLACE INTO waf_config (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )


def _modsec_installed() -> bool:
    result = utils.run_command(["which", "modsec_audit"], check=False)
    if result and result.returncode == 0:
        return True
    return Path(MODSEC_CONF).exists()


def _modsec_enabled_in_nginx() -> bool:
    result = utils.run_command(["nginx", "-V"], check=False)
    if result and result.returncode == 0:
        return "ngx_http_modsecurity" in result.stdout
    return False


def _nginx_modsec_conf() -> str:
    return "/etc/nginx/modsec/"


@router.get("/status")
def get_status(user: dict = Depends(get_current_user)):
    config = _load_waf_config()
    installed = _modsec_installed()
    nginx_enabled = _modsec_enabled_in_nginx()
    with connect() as conn:
        rules_count = conn.execute("SELECT COUNT(*) as c FROM waf_custom_rules").fetchone()["c"]
    return {
        "installed": installed,
        "enabled": config.get("enabled", False),
        "nginx_module": nginx_enabled,
        "rules_loaded": rules_count,
        "custom_rules_count": rules_count,
    }


@router.post("/enable")
def enable_waf(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="WAF management is only supported on Linux")
    if not _modsec_installed():
        raise HTTPException(status_code=400, detail="ModSecurity is not installed")
    conf_path = Path(MODSEC_CONF)
    if conf_path.exists():
        content = conf_path.read_text()
        if "SecRuleEngine Off" in content:
            content = content.replace("SecRuleEngine Off", "SecRuleEngine On")
            conf_path.write_text(content)
    modsec_dir = Path(_nginx_modsec_conf())
    modsec_dir.mkdir(parents=True, exist_ok=True)
    (modsec_dir / "main.conf").write_text("Include /etc/modsecurity/modsecurity.conf\nInclude /etc/modsecurity/rules/*.conf\n")
    utils.service_action("reload", "nginx")
    _save_waf_config({"enabled": True})
    return {"status": "enabled"}


@router.post("/disable")
def disable_waf(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="WAF management is only supported on Linux")
    conf_path = Path(MODSEC_CONF)
    if conf_path.exists():
        content = conf_path.read_text()
        if "SecRuleEngine On" in content:
            content = content.replace("SecRuleEngine On", "SecRuleEngine Off")
            conf_path.write_text(content)
    utils.service_action("reload", "nginx")
    _save_waf_config({"enabled": False})
    return {"status": "disabled"}


@router.get("/rules")
def list_rules(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT rule_id, rule_name, pattern, action, phase, severity, description, enabled, created_at FROM waf_custom_rules",
        ).fetchall()
    rules = {r["rule_id"]: dict(r) for r in rows}
    for v in rules.values():
        v["enabled"] = bool(v["enabled"])
    builtin_count = 0
    rules_dir = Path(MODSEC_RULES_DIR)
    if rules_dir.exists():
        builtin_count = len(list(rules_dir.glob("*.conf")))
    return {"custom_rules": rules, "builtin_rules_count": builtin_count}


@router.post("/rules")
def add_rule(body: CustomRuleCreate, user: dict = Depends(get_current_user)):
    import uuid
    rule_id = str(uuid.uuid4())[:8]
    rule_content = (
        f"SecRule {body.pattern} \"{body.action},id:{rule_id},"
        f"phase:{body.phase},severity:{body.severity},"
        f"msg:'{body.description or body.rule_name}'\"\n"
    )
    rules_dir = Path(MODSEC_RULES_DIR)
    rules_dir.mkdir(parents=True, exist_ok=True)
    custom_file = rules_dir / f"custom-{rule_id}.conf"
    custom_file.write_text(rule_content)
    now = datetime.datetime.now().isoformat()
    with connect() as conn:
        conn.execute(
            """INSERT INTO waf_custom_rules
               (rule_id, rule_name, pattern, action, phase, severity, description, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rule_id, body.rule_name, body.pattern, body.action, body.phase,
             body.severity, body.description or "", 1 if body.enabled else 0, now),
        )
    utils.service_action("reload", "nginx")
    return {"status": "created", "rule_id": rule_id}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT rule_id FROM waf_custom_rules WHERE rule_id = ?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")
        conn.execute("DELETE FROM waf_custom_rules WHERE rule_id = ?", (rule_id,))
    custom_file = Path(MODSEC_RULES_DIR) / f"custom-{rule_id}.conf"
    if custom_file.exists():
        custom_file.unlink()
    utils.service_action("reload", "nginx")
    return {"status": "deleted", "rule_id": rule_id}
