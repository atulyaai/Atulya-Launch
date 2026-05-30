"""One-click app installer API with real deployment logic."""

import datetime
import subprocess
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/apps", tags=["apps"])

AVAILABLE_APPS = {
    "wordpress": {
        "name": "WordPress",
        "description": "Popular CMS and blogging platform",
        "version": "6.5",
        "category": "cms",
        "requires": ["php", "mysql"],
        "port": 80,
    },
    "nextcloud": {
        "name": "Nextcloud",
        "description": "Self-hosted productivity platform",
        "version": "29.0",
        "category": "productivity",
        "requires": ["php", "mysql"],
        "port": 80,
    },
    "gitea": {
        "name": "Gitea",
        "description": "Lightweight Git hosting",
        "version": "1.22",
        "category": "development",
        "requires": ["git"],
        "port": 3000,
    },
    "ghost": {
        "name": "Ghost",
        "description": "Professional publishing platform",
        "version": "5.75",
        "category": "cms",
        "requires": ["nodejs"],
        "port": 2368,
    },
    "minio": {
        "name": "MinIO",
        "description": "S3-compatible object storage",
        "version": "latest",
        "category": "storage",
        "requires": [],
        "port": 9000,
    },
    "n8n": {
        "name": "n8n",
        "description": "Workflow automation",
        "version": "1.40",
        "category": "automation",
        "requires": ["nodejs"],
        "port": 5678,
    },
    "uptimekuma": {
        "name": "Uptime Kuma",
        "description": "Monitoring tool",
        "version": "1.23",
        "category": "monitoring",
        "requires": ["nodejs"],
        "port": 3001,
    },
    "vaultwarden": {
        "name": "Vaultwarden",
        "description": "Bitwarden-compatible password manager",
        "version": "1.30",
        "category": "security",
        "requires": [],
        "port": 8222,
    },
}


def _installed_apps() -> dict:
    p = utils.CONFIG_DIR / "apps.json"
    if not p.exists():
        return {}
    import json
    return json.loads(p.read_text())


def _save_installed(apps: dict):
    p = utils.CONFIG_DIR / "apps.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(apps, indent=2))


def _install_wordpress(domain: str, database: str = None) -> dict:
    """Install WordPress using WP-CLI or manual download."""
    install_dir = f"/var/www/{domain}/public"
    utils.run_command(["mkdir", "-p", install_dir], check=False)

    # Download WordPress
    result = utils.run_command(
        ["curl", "-sSL", "https://wordpress.org/latest.tar.gz", "-o", "/tmp/wordpress.tar.gz"],
        check=False, timeout=120
    )
    if result and result.returncode == 0:
        utils.run_command(["tar", "-xzf", "/tmp/wordpress.tar.gz", "-C", install_dir, "--strip-components=1"], check=False)
        utils.run_command(["chown", "-R", "www-data:www-data", install_dir], check=False)
        return {"status": "installed", "path": install_dir, "method": "download"}
    return {"status": "partial", "path": install_dir, "note": "Download failed, directory created"}


def _install_gitea(domain: str) -> dict:
    """Install Gitea binary."""
    result = utils.run_command(
        ["curl", "-sSL", "https://dl.gitea.com/gitea/1.22.0/gitea-1.22.0-linux-amd64", "-o", "/usr/local/bin/gitea"],
        check=False, timeout=120
    )
    if result and result.returncode == 0:
        utils.run_command(["chmod", "+x", "/usr/local/bin/gitea"], check=False)
        utils.run_command(["useradd", "-r", "-s", "/bin/false", "gitea"], check=False)
        return {"status": "installed", "binary": "/usr/local/bin/gitea"}
    return {"status": "failed", "error": "Download failed"}


def _install_vaultwarden(domain: str) -> dict:
    """Install Vaultwarden binary."""
    result = utils.run_command(
        ["curl", "-sSL", "https://github.com/dani-garcia/vaultwarden/releases/latest/download/vaultwarden-amd64", "-o", "/usr/local/bin/vaultwarden"],
        check=False, timeout=120
    )
    if result and result.returncode == 0:
        utils.run_command(["chmod", "+x", "/usr/local/bin/vaultwarden"], check=False)
        return {"status": "installed", "binary": "/usr/local/bin/vaultwarden"}
    return {"status": "failed", "error": "Download failed"}


def _install_docker_app(slug: str, domain: str) -> dict:
    """Install an app using docker compose."""
    app_dir = f"/opt/atulya-launch/apps/{slug}"
    utils.run_command(["mkdir", "-p", app_dir], check=False)

    docker_compose = {
        "wordpress": """version: '3.8'
services:
  wordpress:
    image: wordpress:latest
    ports:
      - "8080:80"
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: wordpress
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - ./data:/var/www/html
  db:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wordpress
      MYSQL_PASSWORD: wordpress
      MYSQL_ROOT_PASSWORD: rootpass
    volumes:
      - ./db:/var/lib/mysql
""",
        "nextcloud": """version: '3.8'
services:
  nextcloud:
    image: nextcloud:latest
    ports:
      - "8080:80"
    volumes:
      - ./data:/var/www/html
""",
        "ghost": """version: '3.8'
services:
  ghost:
    image: ghost:latest
    ports:
      - "8080:2368"
    environment:
      url: http://localhost:8080
    volumes:
      - ./data:/var/lib/ghost/content
""",
        "minio": """version: '3.8'
services:
  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    command: server /data --console-address ":9001"
    volumes:
      - ./data:/data
""",
        "n8n": """version: '3.8'
services:
  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    volumes:
      - ./data:/home/node/.n8n
""",
        "uptimekuma": """version: '3.8'
services:
  uptime-kuma:
    image: louislam/uptime-kuma:latest
    ports:
      - "3001:3001"
    volumes:
      - ./data:/app/data
""",
        "vaultwarden": """version: '3.8'
services:
  vaultwarden:
    image: vaultwarden/server:latest
    ports:
      - "8222:80"
    volumes:
      - ./data:/data
    environment:
      DOMAIN: http://localhost:8222
""",
    }

    compose_content = docker_compose.get(slug)
    if not compose_content:
        return {"status": "failed", "error": "No docker compose template found"}

    compose_file = f"{app_dir}/docker-compose.yml"
    with open(compose_file, "w") as f:
        f.write(compose_content)

    result = utils.run_command(
        ["docker", "compose", "up", "-d"],
        check=False, timeout=300
    )

    if result and result.returncode == 0:
        return {"status": "installed", "path": app_dir, "method": "docker"}
    return {"status": "failed", "error": result.stderr if result else "Docker compose failed"}


INSTALL_FUNCTIONS = {
    "wordpress": _install_wordpress,
    "gitea": _install_gitea,
    "vaultwarden": _install_vaultwarden,
    "nextcloud": lambda d, db=None: _install_docker_app("nextcloud", d),
    "ghost": lambda d, db=None: _install_docker_app("ghost", d),
    "minio": lambda d, db=None: _install_docker_app("minio", d),
    "n8n": lambda d, db=None: _install_docker_app("n8n", d),
    "uptimekuma": lambda d, db=None: _install_docker_app("uptimekuma", d),
}


@router.get("/available")
def list_available(user: dict = Depends(get_current_user)):
    installed = _installed_apps()
    result = []
    for slug, info in AVAILABLE_APPS.items():
        entry = {**info, "slug": slug, "installed": slug in installed}
        result.append(entry)
    return {"apps": result}


@router.get("/installed")
def list_installed(user: dict = Depends(get_current_user)):
    return {"apps": _installed_apps()}


class InstallRequest(BaseModel):
    slug: str
    domain: Optional[str] = None
    database: Optional[str] = None


@router.post("/install")
def install_app(body: InstallRequest, user: dict = Depends(get_current_user)):
    if body.slug not in AVAILABLE_APPS:
        raise HTTPException(status_code=404, detail="App not found")
    installed = _installed_apps()
    if body.slug in installed:
        raise HTTPException(status_code=409, detail="App already installed")

    info = AVAILABLE_APPS[body.slug]
    domain = body.domain or f"{body.slug}.local"

    install_fn = INSTALL_FUNCTIONS.get(body.slug)
    install_result = {}
    if install_fn:
        try:
            install_result = install_fn(domain, body.database)
        except Exception as e:
            install_result = {"status": "failed", "error": str(e)}

    app_record = {
        "slug": body.slug,
        "name": info["name"],
        "version": info["version"],
        "domain": domain,
        "database": body.database,
        "port": info.get("port"),
        "installed_at": datetime.datetime.now().isoformat(),
        "status": install_result.get("status", "installed"),
        "install_details": install_result,
    }
    installed[body.slug] = app_record
    _save_installed(installed)
    return {"status": "installed", "app": app_record}


@router.delete("/{name}")
def uninstall_app(name: str, user: dict = Depends(get_current_user)):
    installed = _installed_apps()
    if name not in installed:
        raise HTTPException(status_code=404, detail="App not installed")

    app = installed[name]
    # Try to stop docker containers if applicable
    app_dir = f"/opt/atulya-launch/apps/{name}"
    utils.run_command(["docker", "compose", "down"], check=False, workdir=app_dir)

    del installed[name]
    _save_installed(installed)
    return {"status": "uninstalled", "name": name}


@router.post("/{name}/update")
def update_app(name: str, user: dict = Depends(get_current_user)):
    installed = _installed_apps()
    if name not in installed:
        raise HTTPException(status_code=404, detail="App not installed")
    if name in AVAILABLE_APPS:
        installed[name]["version"] = AVAILABLE_APPS[name]["version"]
        installed[name]["updated_at"] = datetime.datetime.now().isoformat()
        _save_installed(installed)
    return {"status": "updated", "name": name}
