"""Email alert rules API — CPU, disk, SSL, service, backup alerts."""

import datetime
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

ALERTS_FILE = utils.CONFIG_DIR / "alerts.json"


class AlertRuleCreate(BaseModel):
    name: str
    alert_type: str
    threshold: Optional[float] = None
    email: str
    enabled: bool = True
    check_interval: int = 300
    extra: Optional[dict] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    threshold: Optional[float] = None
    email: Optional[str] = None
    enabled: Optional[bool] = None
    check_interval: Optional[int] = None
    extra: Optional[dict] = None


VALID_TYPES = {"high_cpu", "disk_full", "ssl_expiry", "service_down", "backup_failure"}


def _load_alerts() -> dict:
    if ALERTS_FILE.exists():
        import json
        return json.loads(ALERTS_FILE.read_text())
    return {"rules": {}, "notification_email": "", "history": []}


def _save_alerts(data: dict):
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    ALERTS_FILE.write_text(json.dumps(data, indent=2))


@router.get("")
def list_rules(user: dict = Depends(get_current_user)):
    data = _load_alerts()
    return {"rules": data.get("rules", {}), "notification_email": data.get("notification_email", "")}


@router.post("")
def create_rule(body: AlertRuleCreate, user: dict = Depends(get_current_user)):
    if body.alert_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid alert_type. Must be one of: {', '.join(VALID_TYPES)}")
    data = _load_alerts()
    rule_id = str(uuid.uuid4())[:8]
    data.setdefault("rules", {})[rule_id] = {
        "id": rule_id,
        "name": body.name,
        "alert_type": body.alert_type,
        "threshold": body.threshold,
        "email": body.email,
        "enabled": body.enabled,
        "check_interval": body.check_interval,
        "extra": body.extra or {},
        "created_at": datetime.datetime.now().isoformat(),
    }
    _save_alerts(data)
    return {"status": "created", "rule_id": rule_id}


@router.put("/{rule_id}")
def update_rule(rule_id: str, body: AlertRuleUpdate, user: dict = Depends(get_current_user)):
    data = _load_alerts()
    rules = data.get("rules", {})
    if rule_id not in rules:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    rule = rules[rule_id]
    for field, value in body.dict(exclude_unset=True).items():
        rule[field] = value
    rule["updated_at"] = datetime.datetime.now().isoformat()
    _save_alerts(data)
    return {"status": "updated", "rule": rule}


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, user: dict = Depends(get_current_user)):
    data = _load_alerts()
    rules = data.get("rules", {})
    if rule_id not in rules:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    del rules[rule_id]
    _save_alerts(data)
    return {"status": "deleted", "rule_id": rule_id}


@router.put("/notification-email")
def set_notification_email(body: dict, user: dict = Depends(get_current_user)):
    email = body.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    data = _load_alerts()
    data["notification_email"] = email
    _save_alerts(data)
    return {"status": "updated", "notification_email": email}


@router.get("/history")
def alert_history(user: dict = Depends(get_current_user)):
    data = _load_alerts()
    return {"history": data.get("history", [])[-50:]}


@router.post("/check")
def check_alerts(user: dict = Depends(get_current_user)):
    data = _load_alerts()
    triggered = []
    try:
        status_data = _get_system_status()
    except Exception:
        return {"triggered": [], "error": "Could not retrieve system status"}
    rules = data.get("rules", {})
    for rule_id, rule in rules.items():
        if not rule.get("enabled"):
            continue
        alert_type = rule.get("alert_type")
        threshold = rule.get("threshold", 80)
        fired = False
        if alert_type == "high_cpu" and status_data.get("cpu_percent", 0) > threshold:
            fired = True
        elif alert_type == "disk_full" and status_data.get("disk_percent", 0) > threshold:
            fired = True
        if fired:
            entry = {
                "rule_id": rule_id,
                "alert_type": alert_type,
                "message": f"{rule.get('name', alert_type)} triggered at {datetime.datetime.now().isoformat()}",
                "email": rule.get("email", ""),
                "timestamp": datetime.datetime.now().isoformat(),
            }
            data.setdefault("history", []).append(entry)
            triggered.append(entry)
    _save_alerts(data)
    return {"triggered": triggered, "checked_at": datetime.datetime.now().isoformat()}


def _get_system_status() -> dict:
    try:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "disk_percent": psutil.disk_usage("/").percent,
            "memory_percent": psutil.virtual_memory().percent,
        }
    except ImportError:
        return {"cpu_percent": 0, "disk_percent": 0, "memory_percent": 0}
