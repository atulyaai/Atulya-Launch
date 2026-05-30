"""NGINX Reverse Proxy Management API."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/nginx", tags=["nginx-proxy"])

NGINX_SITES_AVAILABLE = "/etc/nginx/sites-available"
NGINX_SITES_ENABLED = "/etc/nginx/sites-enabled"
UPSTREAMS_CONF = "/etc/nginx/conf.d/upstreams.conf"
PROXY_CONFIG_FILE = utils.CONFIG_DIR / "nginx_proxy.json"


def _load_proxy_config() -> dict:
    if PROXY_CONFIG_FILE.exists():
        with open(PROXY_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_proxy_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROXY_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _site_config_path(domain: str) -> Path:
    return Path(NGINX_SITES_AVAILABLE) / domain


def _generate_proxy_config(
    domain: str,
    upstream: str,
    port: int = 8080,
    websocket: bool = False,
    headers: Optional[dict] = None,
    extra: Optional[str] = None,
) -> str:
    lines = [
        f"server {{",
        f"    listen 80;",
        f"    server_name {domain};",
        f"",
        f"    location / {{",
        f"        proxy_pass http://127.0.0.1:{port};",
        f"        proxy_set_header Host $host;",
        f"        proxy_set_header X-Real-IP $remote_addr;",
        f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        f"        proxy_set_header X-Forwarded-Proto $scheme;",
    ]

    if websocket:
        lines.extend([
            f"        proxy_http_version 1.1;",
            f"        proxy_set_header Upgrade $http_upgrade;",
            f"        proxy_set_header Connection \"upgrade\";",
            f"        proxy_read_timeout 86400;",
        ])

    if headers:
        for key, value in headers.items():
            lines.append(f"        proxy_set_header {key} {value};")

    lines.extend([
        f"    }}",
        f"}}",
    ])

    if extra:
        lines.insert(-1, extra)

    return "\n".join(lines) + "\n"


def _generate_upstream_block(name: str, servers: list) -> str:
    lines = [f"upstream {name} {{"]
    for server in servers:
        weight = server.get("weight", 1)
        backup = " backup" if server.get("backup") else ""
        lines.append(f"    server {server['host']}:{server['port']} weight={weight}{backup};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _parse_upstreams_from_file() -> list:
    if not Path(UPSTREAMS_CONF).exists():
        return []
    content = Path(UPSTREAMS_CONF).read_text()
    upstreams = []
    for match in re.finditer(r"upstream\s+(\w+)\s*\{([^}]+)\}", content):
        name = match.group(1)
        block = match.group(2)
        servers = []
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("server"):
                parts = line.split()
                if len(parts) >= 2:
                    server_addr = parts[1].rstrip(";")
                    host_port = server_addr.split(":")
                    servers.append({
                        "host": host_port[0] if len(host_port) > 1 else "127.0.0.1",
                        "port": int(host_port[1]) if len(host_port) > 1 else 80,
                        "weight": 1,
                        "backup": "backup" in line,
                    })
        upstreams.append({"name": name, "servers": servers})
    return upstreams


class ProxyConfig(BaseModel):
    upstream: str = "backend"
    port: int = 8080
    websocket: bool = False
    headers: Optional[dict] = None
    extra_config: Optional[str] = None


class UpstreamServer(BaseModel):
    host: str = "127.0.0.1"
    port: int
    weight: int = 1
    backup: bool = False


class UpstreamCreate(BaseModel):
    name: str
    servers: list[UpstreamServer]


@router.get("/proxy/{domain}")
def get_proxy_config(domain: str, user: dict = Depends(get_current_user)):
    config_path = _site_config_path(domain)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Proxy config not found")

    content = config_path.read_text()
    proxy_data = _load_proxy_config()
    domain_config = proxy_data.get(domain, {})

    return {
        "domain": domain,
        "config_path": str(config_path),
        "content": content,
        "metadata": domain_config,
    }


@router.put("/proxy/{domain}")
def set_proxy_config(domain: str, body: ProxyConfig, user: dict = Depends(get_current_user)):
    config_content = _generate_proxy_config(
        domain=domain,
        upstream=body.upstream,
        port=body.port,
        websocket=body.websocket,
        headers=body.headers,
        extra=body.extra_config,
    )

    config_path = _site_config_path(domain)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        f.write(config_content)

    enabled_path = Path(NGINX_SITES_ENABLED) / domain
    if not enabled_path.exists():
        try:
            enabled_path.symlink_to(config_path)
        except FileExistsError:
            pass

    proxy_data = _load_proxy_config()
    proxy_data[domain] = {
        "upstream": body.upstream,
        "port": body.port,
        "websocket": body.websocket,
        "headers": body.headers,
        "updated_at": datetime.now().isoformat(),
    }
    _save_proxy_config(proxy_data)

    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")

    return {"status": "configured", "domain": domain, "config": config_content}


@router.get("/upstreams")
def list_upstreams(user: dict = Depends(get_current_user)):
    upstreams = _parse_upstreams_from_file()
    return {"upstreams": upstreams}


@router.post("/upstreams")
def create_upstream(body: UpstreamCreate, user: dict = Depends(get_current_user)):
    upstream_block = _generate_upstream_block(body.name, [s.model_dump() for s in body.servers])

    Path(NGINX_SITES_AVAILABLE).mkdir(parents=True, exist_ok=True)
    conf_path = Path(UPSTREAMS_CONF)

    existing = ""
    if conf_path.exists():
        existing = conf_path.read_text()
        existing = re.sub(rf"upstream\s+{re.escape(body.name)}\s*\{{[^}}]+\}}", "", existing)
        existing = existing.strip()

    new_content = existing + "\n\n" + upstream_block if existing else upstream_block
    conf_path.write_text(new_content)

    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")

    return {"status": "created", "upstream": body.name, "servers": body.servers}


@router.delete("/upstreams/{name}")
def delete_upstream(name: str, user: dict = Depends(get_current_user)):
    if not Path(UPSTREAMS_CONF).exists():
        raise HTTPException(status_code=404, detail="Upstreams config not found")

    content = Path(UPSTREAMS_CONF).read_text()
    new_content = re.sub(rf"upstream\s+{re.escape(name)}\s*\{{[^}}]+\}}", "", content).strip()

    if new_content == content:
        raise HTTPException(status_code=404, detail="Upstream not found")

    Path(UPSTREAMS_CONF).write_text(new_content)
    utils.run_command(["nginx", "-t"], check=False)
    utils.service_action("reload", "nginx")

    return {"status": "deleted", "upstream": name}


@router.post("/proxy/{domain}/reload")
def reload_proxy(domain: str, user: dict = Depends(get_current_user)):
    config_path = _site_config_path(domain)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Proxy config not found")

    result = utils.run_command(["nginx", "-t"], check=False)
    if result and result.returncode != 0:
        raise HTTPException(status_code=500, detail="NGINX config test failed")

    utils.service_action("reload", "nginx")
    return {"status": "reloaded", "domain": domain}
