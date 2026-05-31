"""Docker fallback mode for services not available natively."""

from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .base import ApplyResult


def _run(command: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=check)


@dataclass(slots=True)
class DockerFallback:
    """Provides Docker containers when native services are unavailable."""

    dry_run: bool = True

    def is_docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def ensure_service(self, image: str, name: str, ports: dict[str, str], volumes: dict[str, str], env: dict[str, str] | None = None) -> ApplyResult:
        """Ensure a Docker container is running for a service."""
        if not self.is_docker_available():
            return ApplyResult(ok=False, action="docker_unavailable", message="Docker is not installed")

        running = _run(["docker", "inspect", "-f", "{{.State.Running}}", name])
        if running.stdout.strip() == "true":
            return ApplyResult(ok=True, action="docker_already_running", message=f"{name} is already running")

        cmd = ["docker", "run", "-d", "--name", name, "--restart", "unless-stopped"]
        for host_port, container_port in ports.items():
            cmd.extend(["-p", f"{host_port}:{container_port}"])
        for host_path, container_path in volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])
        if env:
            for key, value in env.items():
                cmd.extend(["-e", f"{key}={value}"])
        cmd.append(image)

        if self.dry_run:
            return ApplyResult(ok=True, action="docker.dry_run", changed=True, commands=[cmd])

        result = _run(cmd)
        return ApplyResult(
            ok=result.returncode == 0,
            action="docker.start",
            changed=result.returncode == 0,
            message=(result.stdout or result.stderr).strip(),
            commands=[cmd],
        )

    def ensure_nginx(self) -> ApplyResult:
        """Ensure Nginx is available via Docker if not installed natively."""
        if shutil.which("nginx"):
            return ApplyResult(ok=True, action="nginx_native", message="Nginx is installed natively")
        return self.ensure_service(
            image="nginx:alpine",
            name="atulya-nginx",
            ports={"80": "80", "443": "443"},
            volumes={
                "/etc/nginx/sites-available": "/etc/nginx/conf.d",
                "/var/www": "/usr/share/nginx/html",
            },
        )

    def ensure_mysql(self) -> ApplyResult:
        """Ensure MySQL is available via Docker if not installed natively."""
        if shutil.which("mysql"):
            return ApplyResult(ok=True, action="mysql_native", message="MySQL is installed natively")
        return self.ensure_service(
            image="mysql:8",
            name="atulya-mysql",
            ports={"3306": "3306"},
            volumes={
                "/var/lib/mysql": "/var/lib/mysql",
            },
            env={
                "MYSQL_ROOT_PASSWORD": "atulya-root",
                "MYSQL_ALLOW_EMPTY_PASSWORD": "yes",
            },
        )

    def ensure_postgresql(self) -> ApplyResult:
        """Ensure PostgreSQL is available via Docker if not installed natively."""
        if shutil.which("psql"):
            return ApplyResult(ok=True, action="postgresql_native", message="PostgreSQL is installed natively")
        return self.ensure_service(
            image="postgres:16",
            name="atulya-postgres",
            ports={"5432": "5432"},
            volumes={
                "/var/lib/postgresql/data": "/var/lib/postgresql/data",
            },
            env={
                "POSTGRES_HOST_AUTH_METHOD": "trust",
            },
        )

    def ensure_redis(self) -> ApplyResult:
        """Ensure Redis is available via Docker if not installed natively."""
        if shutil.which("redis-cli"):
            return ApplyResult(ok=True, action="redis_native", message="Redis is installed natively")
        return self.ensure_service(
            image="redis:alpine",
            name="atulya-redis",
            ports={"6379": "6379"},
            volumes={},
        )

    def ensure_dovecot(self) -> ApplyResult:
        """Ensure Dovecot is available via Docker."""
        return self.ensure_service(
            image="dovecot/dovecot",
            name="atulya-dovecot",
            ports={"993": "993", "995": "995", "143": "143", "110": "110"},
            volumes={
                "/etc/dovecot": "/etc/dovecot",
                "/var/mail": "/var/mail",
            },
        )

    def ensure_postfix(self) -> ApplyResult:
        """Ensure Postfix is available via Docker."""
        return self.ensure_service(
            image="boky/postfix",
            name="atulya-postfix",
            ports={"25": "25", "587": "587"},
            volumes={
                "/etc/postfix": "/etc/postfix",
            },
        )

    def ensure_fail2ban(self) -> ApplyResult:
        """Ensure Fail2Ban is available via Docker."""
        return self.ensure_service(
            image="crazymax/fail2ban",
            name="atulya-fail2ban",
            ports={},
            volumes={
                "/var/log": "/var/log:ro",
                "/etc/fail2ban": "/etc/fail2ban",
            },
        )

    def ensure_all(self) -> dict[str, ApplyResult]:
        """Ensure all core services are running (native or Docker)."""
        return {
            "nginx": self.ensure_nginx(),
            "mysql": self.ensure_mysql(),
            "redis": self.ensure_redis(),
        }

    def list_containers(self) -> list[dict[str, str]]:
        """List Atulya-managed Docker containers."""
        result = _run(["docker", "ps", "-a", "--filter", "name=atulya-", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"])
        containers = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t")
                if len(parts) >= 2:
                    containers.append({
                        "name": parts[0],
                        "status": parts[1],
                        "ports": parts[2] if len(parts) > 2 else "",
                    })
        return containers

    def stop_container(self, name: str) -> ApplyResult:
        """Stop and remove an Atulya Docker container."""
        _run(["docker", "stop", name])
        result = _run(["docker", "rm", name])
        return ApplyResult(ok=result.returncode == 0, action="docker.remove", message=name)
