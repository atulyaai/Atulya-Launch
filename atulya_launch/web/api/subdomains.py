"""Subdomain management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/subdomains", tags=["subdomains"])

SUBDOMAINS_FILE = utils.CONFIG_DIR / "subdomains.json"


def _load_subdomains() -> dict:
    if SUBDOMAINS_FILE.exists():
        import json
        with open(SUBDOMAINS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_subdomains(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    import json
    with open(SUBDOMAINS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _next_id(data: dict) -> int:
    if not data:
        return 1
    return max(int(k) for k in data.keys()) + 1


class SubdomainCreate(BaseModel):
    domain: str
    subdomain: str
    target: str


class SubdomainUpdate(BaseModel):
    target: Optional[str] = None
    subdomain: Optional[str] = None


@router.get("")
def list_subdomains(user: dict = Depends(get_current_user)):
    data = _load_subdomains()
    return {"subdomains": data}


@router.post("")
def create_subdomain(body: SubdomainCreate, user: dict = Depends(get_current_user)):
    data = _load_subdomains()
    # Check for duplicate
    for entry in data.values():
        if entry.get("domain") == body.domain and entry.get("subdomain") == body.subdomain:
            raise HTTPException(status_code=400, detail="Subdomain already exists")
    nid = _next_id(data)
    record = {
        "domain": body.domain,
        "subdomain": body.subdomain,
        "target": body.target,
        "created_by": user.get("sub", "admin"),
    }
    data[str(nid)] = record
    _save_subdomains(data)
    # Add nginx config if Linux
    if utils.is_linux():
        conf = (
            f"server {{\n"
            f"    listen 80;\n"
            f"    server_name {body.subdomain}.{body.domain};\n"
            f"    location / {{\n"
            f"        proxy_pass {body.target};\n"
            f"        proxy_set_header Host $host;\n"
            f"        proxy_set_header X-Real-IP $remote_addr;\n"
            f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            f"        proxy_set_header X-Forwarded-Proto $scheme;\n"
            f"    }}\n"
            f"}}\n"
        )
        conf_path = f"/etc/nginx/sites-available/{body.subdomain}.{body.domain}"
        utils.run_command(["tee", conf_path], check=False)
        # Write via shell since tee might not handle newlines
        utils.run_command(
            ["bash", "-c", f"cat > {conf_path} << 'NGINX_EOF'\n{conf}NGINX_EOF"],
            check=False,
        )
        utils.run_command(
            ["ln", "-sf", conf_path, f"/etc/nginx/sites-enabled/{body.subdomain}.{body.domain}"],
            check=False,
        )
        utils.run_command(["nginx", "-t"], check=False)
        utils.run_command(["systemctl", "reload", "nginx"], check=False)
    return {"status": "created", "id": str(nid)}


@router.delete("/{subdomain_id}")
def delete_subdomain(subdomain_id: str, user: dict = Depends(get_current_user)):
    data = _load_subdomains()
    if subdomain_id not in data:
        raise HTTPException(status_code=404, detail="Subdomain not found")
    entry = data.pop(subdomain_id)
    _save_subdomains(data)
    if utils.is_linux():
        full = f"{entry.get('subdomain')}.{entry.get('domain')}"
        utils.run_command(["rm", "-f", f"/etc/nginx/sites-available/{full}"], check=False)
        utils.run_command(["rm", "-f", f"/etc/nginx/sites-enabled/{full}"], check=False)
        utils.run_command(["nginx", "-t"], check=False)
        utils.run_command(["systemctl", "reload", "nginx"], check=False)
    return {"status": "deleted", "id": subdomain_id}


@router.put("/{subdomain_id}")
def update_subdomain(subdomain_id: str, body: SubdomainUpdate, user: dict = Depends(get_current_user)):
    data = _load_subdomains()
    if subdomain_id not in data:
        raise HTTPException(status_code=404, detail="Subdomain not found")
    if body.target is not None:
        data[subdomain_id]["target"] = body.target
    if body.subdomain is not None:
        data[subdomain_id]["subdomain"] = body.subdomain
    _save_subdomains(data)
    return {"status": "updated", "id": subdomain_id, "entry": data[subdomain_id]}
