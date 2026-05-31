"""Reseller Limits - Quota management and white-label branding."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/reseller", tags=["reseller"])

RESELLER_DIR = utils.CONFIG_DIR / "reseller"
PLANS_FILE = RESELLER_DIR / "plans.json"
USERS_FILE = RESELLER_DIR / "users.json"
BRANDING_FILE = RESELLER_DIR / "branding.json"


def _ensure_dirs():
    RESELLER_DIR.mkdir(parents=True, exist_ok=True)
    if not PLANS_FILE.exists():
        default_plans = [
            {
                "id": "free",
                "name": "Free",
                "max_sites": 2,
                "max_email_accounts": 5,
                "max_databases": 2,
                "max_disk_mb": 1024,
                "max_bandwidth_gb": 10,
                "max_subdomains": 5,
                "max_ssl_certs": 1,
                "max_backups": 2,
                "price_monthly": 0,
            },
            {
                "id": "starter",
                "name": "Starter",
                "max_sites": 10,
                "max_email_accounts": 50,
                "max_databases": 10,
                "max_disk_mb": 10240,
                "max_bandwidth_gb": 100,
                "max_subdomains": 25,
                "max_ssl_certs": 10,
                "max_backups": 10,
                "price_monthly": 9.99,
            },
            {
                "id": "professional",
                "name": "Professional",
                "max_sites": 50,
                "max_email_accounts": 250,
                "max_databases": 50,
                "max_disk_mb": 51200,
                "max_bandwidth_gb": 500,
                "max_subdomains": 100,
                "max_ssl_certs": 50,
                "max_backups": 50,
                "price_monthly": 29.99,
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "max_sites": -1,
                "max_email_accounts": -1,
                "max_databases": -1,
                "max_disk_mb": -1,
                "max_bandwidth_gb": -1,
                "max_subdomains": -1,
                "max_ssl_certs": -1,
                "max_backups": -1,
                "price_monthly": 99.99,
            },
        ]
        PLANS_FILE.write_text(json.dumps(default_plans, indent=2))
    if not USERS_FILE.exists():
        USERS_FILE.write_text(json.dumps({}, indent=2))
    if not BRANDING_FILE.exists():
        BRANDING_FILE.write_text(json.dumps({
            "company_name": "Atulya Launch",
            "logo_url": "",
            "primary_color": "#4f46e5",
            "footer_text": "Powered by Atulya Launch",
            "custom_css": "",
            "favicon_url": "",
        }, indent=2))


def _load_plans() -> list:
    _ensure_dirs()
    return json.loads(PLANS_FILE.read_text())


def _save_plans(data: list):
    _ensure_dirs()
    PLANS_FILE.write_text(json.dumps(data, indent=2))


def _load_user_plans() -> dict:
    _ensure_dirs()
    return json.loads(USERS_FILE.read_text())


def _save_user_plans(data: dict):
    _ensure_dirs()
    USERS_FILE.write_text(json.dumps(data, indent=2))


def _load_branding() -> dict:
    _ensure_dirs()
    return json.loads(BRANDING_FILE.read_text())


def _save_branding(data: dict):
    _ensure_dirs()
    BRANDING_FILE.write_text(json.dumps(data, indent=2))


def _count_usage(username: str) -> dict:
    config = utils.load_config()
    sites = config.get("sites", {})
    email_data = {}
    email_file = utils.CONFIG_DIR / "email.json"
    if email_file.exists():
        email_data = json.loads(email_file.read_text())

    db_data = config.get("databases", {})
    ssl_data = config.get("ssl", {})
    backup_data = config.get("backups", {})

    site_count = sum(1 for s in sites.values() if s.get("owner") == username)
    email_count = sum(1 for addr in email_data.get("accounts", {}) if addr.endswith(f"@{username}"))
    db_count = sum(1 for db in db_data.values() if db.get("owner") == username)

    return {
        "sites": site_count,
        "email_accounts": email_count,
        "databases": db_count,
    }


class PlanCreate(BaseModel):
    id: str
    name: str
    max_sites: int = 10
    max_email_accounts: int = 50
    max_databases: int = 10
    max_disk_mb: int = 10240
    max_bandwidth_gb: int = 100
    max_subdomains: int = 25
    max_ssl_certs: int = 10
    max_backups: int = 10
    price_monthly: float = 0.0


class BrandingUpdate(BaseModel):
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    footer_text: Optional[str] = None
    custom_css: Optional[str] = None
    favicon_url: Optional[str] = None


@router.get("/plans")
def list_plans(user: dict = Depends(get_current_user)):
    return {"plans": _load_plans()}


@router.post("/plans")
def create_plan(body: PlanCreate, user: dict = Depends(get_current_user)):
    plans = _load_plans()
    existing = [p for p in plans if p["id"] == body.id]
    if existing:
        raise HTTPException(status_code=409, detail="Plan already exists")

    plan = body.dict()
    plans.append(plan)
    _save_plans(plans)
    return {"status": "created", "plan": plan}


@router.put("/plans/{plan_id}")
def update_plan(plan_id: str, body: PlanCreate, user: dict = Depends(get_current_user)):
    plans = _load_plans()
    for i, p in enumerate(plans):
        if p["id"] == plan_id:
            plans[i] = body.dict()
            _save_plans(plans)
            return {"status": "updated", "plan": plans[i]}
    raise HTTPException(status_code=404, detail="Plan not found")


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: str, user: dict = Depends(get_current_user)):
    plans = _load_plans()
    plans = [p for p in plans if p["id"] != plan_id]
    _save_plans(plans)
    return {"status": "deleted", "plan_id": plan_id}


@router.get("/users")
def list_user_plans(user: dict = Depends(get_current_user)):
    user_plans = _load_user_plans()
    plans = _load_plans()
    result = []
    for username, plan_id in user_plans.items():
        plan = next((p for p in plans if p["id"] == plan_id), None)
        usage = _count_usage(username)
        result.append({
            "username": username,
            "plan_id": plan_id,
            "plan_name": plan["name"] if plan else "Unknown",
            "usage": usage,
            "limits": plan if plan else {},
        })
    return {"users": result}


@router.post("/users/{username}/assign")
def assign_plan(username: str, body: dict, user: dict = Depends(get_current_user)):
    plan_id = body.get("plan_id", "")
    plans = _load_plans()
    plan = next((p for p in plans if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    user_plans = _load_user_plans()
    user_plans[username] = plan_id
    _save_user_plans(user_plans)
    return {"status": "assigned", "username": username, "plan": plan}


@router.get("/users/{username}/limits")
def check_limits(username: str, user: dict = Depends(get_current_user)):
    user_plans = _load_user_plans()
    plan_id = user_plans.get(username)
    if not plan_id:
        return {"limited": False, "message": "No plan assigned (unlimited)"}

    plans = _load_plans()
    plan = next((p for p in plans if p["id"] == plan_id), None)
    if not plan:
        return {"limited": False, "message": "Plan not found"}

    usage = _count_usage(username)
    limits = {}
    exceeded = []

    for key in ["sites", "email_accounts", "databases"]:
        limit = plan.get(f"max_{key}", -1)
        used = usage.get(key, 0)
        if limit == -1:
            limits[key] = {"used": used, "limit": "unlimited", "remaining": "unlimited"}
        else:
            limits[key] = {"used": used, "limit": limit, "remaining": max(0, limit - used)}
            if used >= limit:
                exceeded.append(key)

    return {
        "username": username,
        "plan": plan["name"],
        "limits": limits,
        "exceeded": exceeded,
        "can_create": len(exceeded) == 0,
    }


@router.get("/branding")
def get_branding(user: dict = Depends(get_current_user)):
    return _load_branding()


@router.post("/branding")
def update_branding(body: BrandingUpdate, user: dict = Depends(get_current_user)):
    branding = _load_branding()
    for field in ["company_name", "logo_url", "primary_color", "footer_text", "custom_css", "favicon_url"]:
        value = getattr(body, field)
        if value is not None:
            branding[field] = value
    _save_branding(branding)

    if branding.get("primary_color"):
        css_var = f":root {{ --primary: {branding['primary_color']}; }}"
        css_path = utils.CONFIG_DIR / "custom.css"
        css_path.write_text(css_var)

    return {"status": "updated", "branding": branding}


@router.get("/summary")
def reseller_summary(user: dict = Depends(get_current_user)):
    plans = _load_plans()
    user_plans = _load_user_plans()
    total_users = len(user_plans)
    revenue = 0
    for username, plan_id in user_plans.items():
        plan = next((p for p in plans if p["id"] == plan_id), None)
        if plan:
            revenue += plan.get("price_monthly", 0)

    return {
        "total_plans": len(plans),
        "total_users": total_users,
        "monthly_revenue": revenue,
        "plans": plans,
    }
