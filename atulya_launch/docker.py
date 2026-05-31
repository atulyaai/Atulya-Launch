"""Docker container management helpers for Atulya Launch."""
import json
from pathlib import Path
from typing import Any

from . import core


DOCKER_APPS: dict[str, dict[str, Any]] = {
    "nginx": {"image": "nginx:alpine", "ports": {"80": "80", "443": "443"}, "description": "Nginx web server"},
    "mysql": {"image": "mysql:8", "ports": {"3306": "3306"}, "env": {"MYSQL_ROOT_PASSWORD": "changeme"}, "description": "MySQL database"},
    "postgres": {"image": "postgres:16", "ports": {"5432": "5432"}, "env": {"POSTGRES_PASSWORD": "changeme"}, "description": "PostgreSQL database"},
    "redis": {"image": "redis:alpine", "ports": {"6379": "6379"}, "description": "Redis cache"},
    "memcached": {"image": "memcached:alpine", "ports": {"11211": "11211"}, "description": "Memcached cache"},
    "phpmyadmin": {"image": "phpmyadmin:latest", "ports": {"8081": "80"}, "description": "phpMyAdmin for MySQL"},
    "adminer": {"image": "adminer:latest", "ports": {"8082": "8080"}, "description": "Database management UI"},
    "wordpress": {"image": "wordpress:latest", "ports": {"8083": "80"}, "env": {"WORDPRESS_DB_HOST": "mysql", "WORDPRESS_DB_USER": "root", "WORDPRESS_DB_PASSWORD": "changeme"}, "description": "WordPress CMS"},
    "nextcloud": {"image": "nextcloud:latest", "ports": {"8084": "80"}, "description": "Nextcloud file sharing"},
    "portainer": {"image": "portainer/portainer-ce:latest", "ports": {"9443": "9443"}, "volumes": {"/var/run/docker.sock": "/var/run/docker.sock"}, "description": "Portainer CE"},
}


def docker_available() -> bool:
    """Check if Docker is available on the system."""
    if core.get_platform() != "linux":
        return False
    result = core.run_cmd(["docker", "--version"], check=False)
    return result.returncode == 0


def docker_list_containers(all_containers: bool = False) -> list[dict[str, Any]]:
    """List Docker containers in JSON format."""
    cmd: list[str] = ["docker", "ps", "--format", "{{json .}}"]
    if all_containers:
        cmd.append("-a")
    result = core.run_cmd(cmd, check=False)
    if result.returncode != 0:
        return []
    containers: list[dict[str, Any]] = []
    for line in result.stdout.strip().splitlines():
        if line.strip():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return containers


def docker_list_images() -> list[dict[str, Any]]:
    """List Docker images in JSON format."""
    result = core.run_cmd(["docker", "images", "--format", "{{json .}}"], check=False)
    if result.returncode != 0:
        return []
    images: list[dict[str, Any]] = []
    for line in result.stdout.strip().splitlines():
        if line.strip():
            try:
                images.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return images


def docker_run(name: str, image: str, ports: dict[str, str] | None = None, env: dict[str, str] | None = None, volumes: dict[str, str] | None = None, detach: bool = True) -> dict[str, Any]:
    """Run a new Docker container."""
    cmd: list[str] = ["docker", "run", "-d", "--name", name, "--restart", "unless-stopped"]
    if ports:
        for host_port, container_port in ports.items():
            cmd.extend(["-p", f"{host_port}:{container_port}"])
    if env:
        for k, v in env.items():
            cmd.extend(["-e", f"{k}={v}"])
    if volumes:
        for host_path, container_path in volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])
    cmd.append(image)
    result = core.run_cmd(cmd, check=False)
    return {"ok": result.returncode == 0, "output": result.stdout.strip(), "error": result.stderr.strip()}


def docker_stop(name: str) -> dict[str, bool]:
    """Stop a running Docker container."""
    result = core.run_cmd(["docker", "stop", name], check=False)
    return {"ok": result.returncode == 0}


def docker_start(name: str) -> dict[str, bool]:
    """Start a stopped Docker container."""
    result = core.run_cmd(["docker", "start", name], check=False)
    return {"ok": result.returncode == 0}


def docker_remove(name: str, force: bool = False) -> dict[str, bool]:
    """Remove a Docker container."""
    cmd: list[str] = ["docker", "rm"]
    if force:
        cmd.append("-f")
    cmd.append(name)
    result = core.run_cmd(cmd, check=False)
    return {"ok": result.returncode == 0}


def docker_logs(name: str, lines: int = 100) -> str:
    """Fetch logs from a Docker container."""
    result = core.run_cmd(["docker", "logs", "--tail", str(lines), name], check=False)
    return result.stdout + result.stderr


def docker_pull(image: str) -> dict[str, Any]:
    """Pull a Docker image."""
    result = core.run_cmd(["docker", "pull", image], check=False)
    return {"ok": result.returncode == 0, "output": result.stdout.strip()}
