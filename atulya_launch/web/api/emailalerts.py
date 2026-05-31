"""Email alert rules API — CPU, disk, SSL, service, backup alerts."""

import json
import datetime
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


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


def _load_alert_config() -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM alert_config").fetchall()
    config = {}
    for r in rows:
        try:
            config[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            config[r["key"]] = r["value"]
    return config


def _save_alert_config(data: dict):
    with connect() as conn:
        for key, value in data.items():
            conn.execute(
                "INSERT OR REPLACE INTO alert_config (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )


@router.get("")
def list_rules(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, alert_type, threshold, email, enabled, check_interval, extra_json, created_at, updated_at FROM alert_rules",
        ).fetchall()
    config = _load_alert_config()
    rules = {}
    for r in rows:
        rule = dict(r)
        rule["enabled"] = bool(rule["enabled"])
        try:
            rule["extra"] = json.loads(rule["extra_json"])
        except (json.JSONDecodeError, TypeError):
            rule["extra"] = {}
        del rule["extra_json"]
        rules[rule["id"]] = rule
    return {"rules": rules, "notification_email": config.get("notification_email", "")}


@router.post("")
def create_rule(body: AlertRuleCreate, user: dict = Depends(get_current_user)):
    if body.alert_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid alert_type. Must be one of: {', '.join(VALID_TYPES)}")
    rule_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.now().isoformat()
    with connect() as conn:
        conn.execute(
            """INSERT INTO alert_rules (id, name, alert_type, threshold, email, enabled, check_interval, extra_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rule_id, body.name, body.alert_type, body.threshold, body.email,
             1 if body.enabled else 0, body.check_interval, json.dumps(body.extra or {}), now),
        )
    return {"status": "created", "rule_id": rule_id}


@router.put("/{rule_id}")
def update_rule(rule_id: str, body: AlertRuleUpdate, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        now = datetime.datetime.now().isoformat()
        updates = []
        params = []
        if body.name is not None:
            updates.append("name = ?")
            params.append(body.name)
        if body.threshold is not None:
            updates.append("threshold = ?")
            params.append(body.threshold)
        if body.email is not None:
            updates.append("email = ?")
            params.append(body.email)
        if body.enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if body.enabled else 0)
        if body.check_interval is not None:
            updates.append("check_interval = ?")
            params.append(body.check_interval)
        if body.extra is not None:
            updates.append("extra_json = ?")
            params.append(json.dumps(body.extra))
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(rule_id)
            conn.execute(f"UPDATE alert_rules SET {', '.join(updates)} WHERE id = ?", params)
    return {"status": "updated", "rule_id": rule_id}


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    return {"status": "deleted", "rule_id": rule_id}


@router.put("/notification-email")
def set_notification_email(body: dict, user: dict = Depends(get_current_user)):
    email = body.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    _save_alert_config({"notification_email": email})
    return {"status": "updated", "notification_email": email}


@router.get("/history")
def alert_history(user: dict = Depends(get_current_user)):
    config = _load_alert_config()
    return {"history": config.get("history", [])[-50:]}


@router.post("/check")
def check_alerts(user: dict = Depends(get_current_user)):
    triggered = []
    try:
        status_data = _get_system_status()
    except Exception:
        return {"triggered": [], "error": "Could not retrieve system status"}
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, alert_type, threshold, email, enabled FROM alert_rules WHERE enabled = 1",
        ).fetchall()
    config = _load_alert_config()
    history = config.get("history", [])
    for r in rows:
        alert_type = r["alert_type"]
        threshold = r["threshold"] or 80
        fired = False
        if alert_type == "high_cpu" and status_data.get("cpu_percent", 0) > threshold:
            fired = True
        elif alert_type == "disk_full" and status_data.get("disk_percent", 0) > threshold:
            fired = True
        if fired:
            entry = {
                "rule_id": r["id"],
                "alert_type": alert_type,
                "message": f"{r['name']} triggered at {datetime.datetime.now().isoformat()}",
                "email": r["email"],
                "timestamp": datetime.datetime.now().isoformat(),
            }
            history.append(entry)
            triggered.append(entry)
    _save_alert_config({"history": history[-500:]})
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
