"""WHM-style feature manager + IP pool — define which features users can access."""

import datetime
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect, audit_log

router = APIRouter(prefix="/api/feature-manager", tags=["feature manager"])

# Feature key -> human readable name. Mirrors the panel's feature surface.
KNOWN_FEATURES = [
    ("sites", "Websites"),
    ("databases", "Databases"),
    ("email", "Email"),
    ("dns", "DNS"),
    ("ssl", "SSL Certificates"),
    ("files", "File Manager"),
    ("backups", "Backups"),
    ("firewall", "Firewall"),
    ("ssh", "SSH Access"),
    ("cron", "Cron Jobs"),
    ("docker", "Docker"),
    ("apps", "App Installer"),
    ("reseller", "Reseller Tools"),
    ("subdomains", "Subdomains"),
    ("redirects", "Redirects"),
    ("ftp", "FTP Accounts"),
    ("php", "PHP Configuration"),
    ("logs", "Log Viewer"),
    ("monitoring", "Monitoring"),
    ("notifications", "Notifications"),
]


class FeatureGroupCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    features: list = []


class FeatureGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    features: Optional[list] = None


class UserFeatureAssign(BaseModel):
    features: list = []
    group_id: Optional[str] = None


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


_ALLOWED_FEATURES = {k for k, _ in KNOWN_FEATURES}


def _validate_features(features: list) -> list:
    unknown = [f for f in features if f not in _ALLOWED_FEATURES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown features: {unknown}")
    return list(features)


@router.get("/features")
def list_feature_catalog(user: dict = Depends(get_current_user)):
    return {"features": [{"key": k, "name": v} for k, v in KNOWN_FEATURES]}


@router.get("/groups")
def list_groups(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM feature_groups ORDER BY name").fetchall()
    result = []
    for r in rows:
        r = dict(r)
        r["features"] = json.loads(r.get("features") or "[]")
        result.append(r)
    return {"groups": result}


@router.post("/groups")
def create_group(body: FeatureGroupCreate, user: dict = Depends(get_current_user)):
    body.features = _validate_features(body.features)
    with connect() as conn:
        if conn.execute("SELECT id FROM feature_groups WHERE id = ?", (body.id,)).fetchone():
            raise HTTPException(status_code=409, detail="Group already exists")
        conn.execute(
            "INSERT INTO feature_groups (id, name, description, features) VALUES (?, ?, ?, ?)",
            (body.id, body.name, body.description, json.dumps(body.features)),
        )
    audit_log(user.get("sub", "admin"), "feature_manager.group_create", "ok", {"id": body.id})
    return {"status": "created", "id": body.id}


@router.put("/groups/{group_id}")
def update_group(group_id: str, body: FeatureGroupUpdate, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM feature_groups WHERE id = ?", (group_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Group not found")
        name = body.name if body.name is not None else row["name"]
        description = body.description if body.description is not None else row["description"]
        features = json.loads(row["features"] or "[]")
        if body.features is not None:
            features = _validate_features(body.features)
        conn.execute(
            "UPDATE feature_groups SET name = ?, description = ?, features = ? WHERE id = ?",
            (name, description, json.dumps(features), group_id),
        )
    audit_log(user.get("sub", "admin"), "feature_manager.group_update", "ok", {"id": group_id})
    return {"status": "updated", "id": group_id}


@router.delete("/groups/{group_id}")
def delete_group(group_id: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        conn.execute("DELETE FROM feature_groups WHERE id = ?", (group_id,))
    audit_log(user.get("sub", "admin"), "feature_manager.group_delete", "ok", {"id": group_id})
    return {"status": "deleted", "id": group_id}


@router.get("/user/{username}")
def user_features(username: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT value FROM feature_groups WHERE id = ?", (f"user:{username}",)
        ).fetchone()
    if not rows:
        return {"username": username, "features": sorted(_ALLOWED_FEATURES), "restricted": False}
    return {"username": username, "features": json.loads(rows["value"]), "restricted": True}


@router.post("/user/{username}")
def set_user_features(username: str, body: UserFeatureAssign, user: dict = Depends(get_current_user)):
    body.features = _validate_features(body.features)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO feature_groups (id, name, description, features) VALUES (?, ?, ?, ?)",
            (f"user:{username}", f"user:{username}", "per-user feature override", json.dumps(body.features)),
        )
    audit_log(user.get("sub", "admin"), "feature_manager.user_set", "ok", {"username": username})
    return {"username": username, "features": body.features, "restricted": True}


# ─── IP Pool (WHM-style dedicated/shared IP allocation) ───────────────────

class IpAllocate(BaseModel):
    ip: str
    assigned_to: Optional[str] = None
    pool: str = "default"
    note: str = ""


@router.get("/ips")
def list_ips(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM ip_allocations ORDER BY ip").fetchall()
    return {"ips": [dict(r) for r in rows]}


@router.post("/ips")
def allocate_ip(body: IpAllocate, user: dict = Depends(get_current_user)):
    now = _now()
    try:
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO ip_allocations (ip, assigned_to, pool, note, created_at) VALUES (?, ?, ?, ?, ?)"
                "ON CONFLICT(ip) DO UPDATE SET assigned_to = excluded.assigned_to, pool = excluded.pool, note = excluded.note",
                (body.ip, body.assigned_to, body.pool, body.note, now),
            )
            ip = body.ip
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log(user.get("sub", "admin"), "ip_pool.allocate", "ok", {"ip": body.ip})
    return {"status": "allocated", "ip": ip, "assigned_to": body.assigned_to, "pool": body.pool}


@router.delete("/ips/{ip}")
def deallocate_ip(ip: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        cursor = conn.execute("DELETE FROM ip_allocations WHERE ip = ?", (ip,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="IP not found")
    audit_log(user.get("sub", "admin"), "ip_pool.deallocate", "ok", {"ip": ip})
    return {"status": "deallocated", "ip": ip}