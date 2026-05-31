import json
from pathlib import Path

from . import core


DOCKER_APPS = {
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


def docker_available():
    if core.get_platform() != "linux":
        return False
    result = core.run_cmd(["docker", "--version"], check=False)
    return result.returncode == 0


def docker_list_containers(all_containers=False):
    cmd = ["docker", "ps", "--format", "{{json .}}"]
    if all_containers:
        cmd.append("-a")
    result = core.run_cmd(cmd, check=False)
    if result.returncode != 0:
        return []
    containers = []
    for line in result.stdout.strip().splitlines():
        if line.strip():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return containers


def docker_list_images():
    result = core.run_cmd(["docker", "images", "--format", "{{json .}}"], check=False)
    if result.returncode != 0:
        return []
    images = []
    for line in result.stdout.strip().splitlines():
        if line.strip():
            try:
                images.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return images


def docker_run(name, image, ports=None, env=None, volumes=None, detach=True):
    cmd = ["docker", "run", "-d", "--name", name, "--restart", "unless-stopped"]
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


def docker_stop(name):
    result = core.run_cmd(["docker", "stop", name], check=False)
    return {"ok": result.returncode == 0}


def docker_start(name):
    result = core.run_cmd(["docker", "start", name], check=False)
    return {"ok": result.returncode == 0}


def docker_remove(name, force=False):
    cmd = ["docker", "rm"]
    if force:
        cmd.append("-f")
    cmd.append(name)
    result = core.run_cmd(cmd, check=False)
    return {"ok": result.returncode == 0}


def docker_logs(name, lines=100):
    result = core.run_cmd(["docker", "logs", "--tail", str(lines), name], check=False)
    return result.stdout + result.stderr


def docker_pull(image):
    result = core.run_cmd(["docker", "pull", image], check=False)
    return {"ok": result.returncode == 0, "output": result.stdout.strip()}
