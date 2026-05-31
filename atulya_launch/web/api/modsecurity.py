"""ModSecurity WAF management API."""

import datetime
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/waf", tags=["waf"])

WAF_FILE = utils.CONFIG_DIR / "modsecurity.json"

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


def _load_waf() -> dict:
    if WAF_FILE.exists():
        import json
        return json.loads(WAF_FILE.read_text())
    return {"enabled": False, "rules_loaded": 0, "custom_rules": {}}


def _save_waf(data: dict):
    WAF_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    WAF_FILE.write_text(json.dumps(data, indent=2))


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
    data = _load_waf()
    installed = _modsec_installed()
    nginx_enabled = _modsec_enabled_in_nginx()
    return {
        "installed": installed,
        "enabled": data.get("enabled", False),
        "nginx_module": nginx_enabled,
        "rules_loaded": data.get("rules_loaded", 0),
        "custom_rules_count": len(data.get("custom_rules", {})),
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
    data = _load_waf()
    data["enabled"] = True
    _save_waf(data)
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
    data = _load_waf()
    data["enabled"] = False
    _save_waf(data)
    return {"status": "disabled"}


@router.get("/rules")
def list_rules(user: dict = Depends(get_current_user)):
    data = _load_waf()
    rules = data.get("custom_rules", {})
    builtin_count = 0
    rules_dir = Path(MODSEC_RULES_DIR)
    if rules_dir.exists():
        builtin_count = len(list(rules_dir.glob("*.conf")))
    return {"custom_rules": rules, "builtin_rules_count": builtin_count}


@router.post("/rules")
def add_rule(body: CustomRuleCreate, user: dict = Depends(get_current_user)):
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
    data = _load_waf()
    data.setdefault("custom_rules", {})[rule_id] = {
        "id": rule_id,
        "rule_name": body.rule_name,
        "pattern": body.pattern,
        "action": body.action,
        "phase": body.phase,
        "severity": body.severity,
        "description": body.description,
        "enabled": body.enabled,
        "created_at": datetime.datetime.now().isoformat(),
    }
    data["rules_loaded"] = len(data["custom_rules"])
    _save_waf(data)
    utils.service_action("reload", "nginx")
    return {"status": "created", "rule_id": rule_id}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, user: dict = Depends(get_current_user)):
    data = _load_waf()
    rules = data.get("custom_rules", {})
    if rule_id not in rules:
        raise HTTPException(status_code=404, detail="Rule not found")
    del rules[rule_id]
    data["rules_loaded"] = len(rules)
    _save_waf(data)
    custom_file = Path(MODSEC_RULES_DIR) / f"custom-{rule_id}.conf"
    if custom_file.exists():
        custom_file.unlink()
    utils.service_action("reload", "nginx")
    return {"status": "deleted", "rule_id": rule_id}
