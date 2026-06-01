"""Common dry-run driver helpers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .base import ApplyResult, BindZone


def run_command(command: list[str], dry_run: bool = True) -> ApplyResult:
    """Run or plan a command."""
    if dry_run:
        return ApplyResult(ok=True, action="plan", changed=False, commands=[command])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return ApplyResult(
        ok=result.returncode == 0,
        action="run",
        changed=result.returncode == 0,
        message=(result.stdout or result.stderr).strip(),
        commands=[command],
    )


@dataclass(slots=True)
class PlannedServiceDriver:
    """Service driver that plans commands by default."""

    manager: str
    dry_run: bool = True

    def reload(self, service: str) -> ApplyResult:
        return run_command(self._command("reload", service), self.dry_run)

    def restart(self, service: str) -> ApplyResult:
        return run_command(self._command("restart", service), self.dry_run)

    def status(self, service: str) -> ApplyResult:
        return run_command(self._command("status", service), self.dry_run)

    def _command(self, action: str, service: str) -> list[str]:
        if self.manager == "systemd":
            return ["systemctl", action, service]
        if self.manager == "launchd":
            if action == "reload":
                action = "kickstart"
            return ["launchctl", action, service]
        if self.manager == "windows":
            if action == "reload":
                action = "restart"
            return ["sc.exe", action, service]
        return ["service", service, action]


@dataclass(slots=True)
class PlannedPackageDriver:
    """Package driver that exposes install commands without running them."""

    command_prefix: list[str]
    dry_run: bool = True

    def install(self, packages: list[str]) -> ApplyResult:
        return run_command([*self.command_prefix, *packages], self.dry_run)

    def update(self) -> ApplyResult:
        """Update package lists."""
        if self.command_prefix[0] in ("apt-get", "apt"):
            return run_command(["apt-get", "update", "-qq"], self.dry_run)
        elif self.command_prefix[0] in ("dnf", "yum"):
            return run_command([self.command_prefix[0], "makecache"], self.dry_run)
        elif self.command_prefix[0] == "pacman":
            return run_command(["pacman", "-Sy"], self.dry_run)
        elif self.command_prefix[0] == "brew":
            return run_command(["brew", "update"], self.dry_run)
        elif self.command_prefix[0] == "choco":
            return run_command(["choco", "upgrade", "all", "-y"], self.dry_run)
        return ApplyResult(ok=True, action="update_skip", message="update not supported for this manager")

    def remove(self, packages: list[str]) -> ApplyResult:
        """Remove packages."""
        if self.command_prefix[0] in ("apt-get", "apt"):
            return run_command(["apt-get", "remove", "-y", *packages], self.dry_run)
        elif self.command_prefix[0] in ("dnf", "yum"):
            return run_command([self.command_prefix[0], "remove", "-y", *packages], self.dry_run)
        elif self.command_prefix[0] == "pacman":
            return run_command(["pacman", "-R", "--noconfirm", *packages], self.dry_run)
        elif self.command_prefix[0] == "brew":
            return run_command(["brew", "uninstall", *packages], self.dry_run)
        elif self.command_prefix[0] == "choco":
            return run_command(["choco", "uninstall", *packages, "-y"], self.dry_run)
        return ApplyResult(ok=False, action="remove_fail", message="remove not supported")

    def is_installed(self, package: str) -> bool:
        """Check if a package is installed."""
        if self.command_prefix[0] in ("apt-get", "apt"):
            result = run_command(["dpkg", "-l", package], True)
            return result.ok
        elif self.command_prefix[0] in ("dnf", "yum"):
            result = run_command([self.command_prefix[0], "list", "installed", package], True)
            return result.ok
        elif self.command_prefix[0] == "pacman":
            result = run_command(["pacman", "-Qi", package], True)
            return result.ok
        elif self.command_prefix[0] == "brew":
            result = run_command(["brew", "list", package], True)
            return result.ok
        elif self.command_prefix[0] == "choco":
            result = run_command(["choco", "list", "--local-only", package], True)
            return result.ok
        return False


def detect_package_manager() -> tuple[list[str], str]:
    """Detect the system package manager and return (command_prefix, name)."""
    import sys
    import shutil

    if sys.platform.startswith("linux"):
        if shutil.which("apt-get"):
            return ["apt-get", "install", "-y"], "apt"
        elif shutil.which("dnf"):
            return ["dnf", "install", "-y"], "dnf"
        elif shutil.which("yum"):
            return ["yum", "install", "-y"], "yum"
        elif shutil.which("pacman"):
            return ["pacman", "-S", "--noconfirm"], "pacman"
    elif sys.platform == "darwin":
        if shutil.which("brew"):
            return ["brew", "install"], "brew"
    elif sys.platform == "win32":
        if shutil.which("choco"):
            return ["choco", "install", "-y"], "choco"
        elif shutil.which("winget"):
            return ["winget", "install", "--accept-package-agreements", "--accept-source-agreements"], "winget"
    return ["echo", "UNSUPPORTED:"], "unknown"


@dataclass(slots=True)
class FileWebServerDriver:
    """File-backed web server scaffold."""

    name: str
    config_dir: Path
    service: PlannedServiceDriver
    dry_run: bool = True

    # The binary used to test configuration syntax. Different web servers
    # use different invocations; callers can override via subclasses.
    test_command: tuple[str, ...] = ("nginx", "-t")
    detect_command: tuple[str, ...] = ("nginx", "-v")

    def apply_site(self, domain: str, config: str) -> ApplyResult:
        target = self.config_dir / f"{domain}.conf"
        if not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(config, encoding="utf-8")
        return ApplyResult(
            ok=True,
            action=f"{self.name}.apply_site",
            changed=not self.dry_run,
            files=[target.as_posix()],
        )

    def reload(self) -> ApplyResult:
        return self.service.reload(self.name)

    def test_config(self) -> ApplyResult:
        """Validate the web server configuration without reloading."""
        return run_command(list(self.test_command), self.dry_run)

    def detect(self) -> ApplyResult:
        """Detect which web server binary is installed."""
        return run_command(list(self.detect_command), self.dry_run)


@dataclass(slots=True)
class BindDnsDriver:
    """BIND zone file scaffold."""

    zone_dir: Path
    service: PlannedServiceDriver
    dry_run: bool = True
    named_config: Path | None = None

    MANAGED_BEGIN = "// BEGIN ATULYA LAUNCH MANAGED ZONES"
    MANAGED_END = "// END ATULYA LAUNCH MANAGED ZONES"

    def __post_init__(self) -> None:
        if self.named_config is None:
            self.named_config = self.zone_dir.parent / "named.conf.local"

    def apply_zone(self, zone: BindZone) -> ApplyResult:
        target = self.zone_dir / f"db.{zone.domain}"
        content = self._render_zone(zone)
        zone_line = self._zone_config_line(zone.domain, target)
        if not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            self._upsert_zone_config(zone.domain, zone_line)
        check_result = run_command(["named-checkzone", zone.domain, target.as_posix()], self.dry_run)
        commands = [*check_result.commands]
        if not check_result.ok:
            return ApplyResult(
                ok=False,
                action="bind.apply_zone",
                changed=not self.dry_run,
                message=check_result.message,
                commands=commands,
                files=[target.as_posix(), self.named_config.as_posix()],
            )
        reload_result = run_command(["rndc", "reload", zone.domain], self.dry_run)
        commands.extend(reload_result.commands)
        if not reload_result.ok:
            fallback = self.service.reload("bind9")
            commands.extend(fallback.commands)
            reload_result = ApplyResult(
                ok=fallback.ok,
                action=fallback.action,
                changed=fallback.changed,
                message=fallback.message or reload_result.message,
                commands=commands,
            )
        return ApplyResult(
            ok=reload_result.ok,
            action="bind.apply_zone",
            changed=not self.dry_run,
            message=reload_result.message,
            commands=commands,
            files=[target.as_posix(), self.named_config.as_posix()],
        )

    def delete_zone(self, domain: str) -> ApplyResult:
        target = self.zone_dir / f"db.{domain}"
        if not self.dry_run:
            if target.exists():
                target.unlink()
            self._remove_zone_config(domain)
        reload_result = run_command(["rndc", "reload"], self.dry_run)
        commands = [*reload_result.commands]
        if not reload_result.ok:
            fallback = self.service.reload("bind9")
            commands.extend(fallback.commands)
            reload_result = ApplyResult(
                ok=fallback.ok,
                action=fallback.action,
                changed=fallback.changed,
                message=fallback.message or reload_result.message,
                commands=commands,
            )
        return ApplyResult(
            ok=reload_result.ok,
            action="bind.delete_zone",
            changed=not self.dry_run,
            message=reload_result.message,
            commands=commands,
            files=[target.as_posix(), self.named_config.as_posix()],
        )

    def _render_zone(self, zone: BindZone) -> str:
        lines = [
            "$TTL 3600",
            f"@ IN SOA ns1.{zone.domain}. admin.{zone.domain}. ({zone.serial} 3600 1800 1209600 3600)",
            f"@ IN NS ns1.{zone.domain}.",
        ]
        for record in zone.records:
            name = str(record.get("name", "@"))
            record_type = str(record.get("type", "A")).upper()
            value = str(record.get("value", "127.0.0.1"))
            ttl = int(record.get("ttl", 3600))
            lines.append(f"{name} {ttl} IN {record_type} {value}")
        return "\n".join(lines) + "\n"

    def _zone_config_line(self, domain: str, zone_file: Path) -> str:
        return f'zone "{domain}" {{ type master; file "{zone_file.as_posix()}"; }};'

    def _read_named_config(self) -> str:
        if self.named_config and self.named_config.exists():
            return self.named_config.read_text(encoding="utf-8")
        return "// Atulya Launch BIND local configuration\n"

    def _write_named_config(self, zones: dict[str, str]) -> None:
        if self.named_config is None:
            return
        existing = self._read_named_config()
        before, _, tail = existing.partition(self.MANAGED_BEGIN)
        _, _, after = tail.partition(self.MANAGED_END)
        managed_lines = [self.MANAGED_BEGIN, *[zones[domain] for domain in sorted(zones)], self.MANAGED_END]
        content = before.rstrip() + "\n\n" + "\n".join(managed_lines) + "\n" + after.lstrip()
        self.named_config.parent.mkdir(parents=True, exist_ok=True)
        self.named_config.write_text(content, encoding="utf-8")

    def _managed_zones(self) -> dict[str, str]:
        existing = self._read_named_config()
        _, marker, tail = existing.partition(self.MANAGED_BEGIN)
        if not marker:
            return {}
        managed, _, _ = tail.partition(self.MANAGED_END)
        zones: dict[str, str] = {}
        for line in managed.splitlines():
            stripped = line.strip()
            if not stripped.startswith('zone "'):
                continue
            domain = stripped.split('"', 2)[1]
            zones[domain] = stripped
        return zones

    def _upsert_zone_config(self, domain: str, line: str) -> None:
        zones = self._managed_zones()
        zones[domain] = line
        self._write_named_config(zones)

    def _remove_zone_config(self, domain: str) -> None:
        zones = self._managed_zones()
        zones.pop(domain, None)
        self._write_named_config(zones)


@dataclass(slots=True)
class PlannedMailDriver:
    """Postfix/Dovecot mailbox scaffold."""

    config_dir: Path
    service: PlannedServiceDriver
    dry_run: bool = True

    def apply_domain(self, domain: str, mailboxes: list[dict[str, str | int]]) -> ApplyResult:
        target = self.config_dir / "virtual_mailboxes"
        new_lines = [f"{box.get('mailbox')}@{domain} {domain}/{box.get('mailbox')}/" for box in mailboxes]

        if not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = ""
            if target.exists():
                existing = target.read_text(encoding="utf-8")
            other_domains = [
                line for line in existing.splitlines()
                if line.strip() and not line.strip().endswith(f"@{domain} ")
            ]
            all_lines = other_domains + new_lines
            target.write_text("\n".join(all_lines) + "\n", encoding="utf-8")

        postfix = self.service.reload("postfix")
        dovecot = self.service.reload("dovecot")
        return ApplyResult(
            ok=postfix.ok and dovecot.ok,
            action="mail.apply_domain",
            changed=not self.dry_run,
            commands=[*postfix.commands, *dovecot.commands],
            files=[target.as_posix()],
        )


@dataclass(slots=True)
class PhpFpmDriver:
    """PHP-FPM pool configuration and service management."""

    pool_dir: Path
    service: PlannedServiceDriver
    dry_run: bool = True

    POOL_TEMPLATE = """\
[{{domain}}]
user = www-data
group = www-data
listen = /run/php/php{{version}}-fpm-{{domain}}.sock
listen.owner = www-data
listen.group = www-data
pm = dynamic
pm.max_children = 5
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 3
pm.max_requests = 500
php_admin_value[error_log] = /var/log/php{{version}}-fpm-{{domain}}.error.log
php_admin_flag[log_errors] = on
"""

    def install_pool(self, domain: str, version: str) -> ApplyResult:
        """Write a PHP-FPM pool config for a domain."""
        pool_file = self.pool_dir / f"{domain}.conf"
        content = self.POOL_TEMPLATE.replace("{{domain}}", domain).replace("{{version}}", version)
        if not self.dry_run:
            pool_file.parent.mkdir(parents=True, exist_ok=True)
            pool_file.write_text(content, encoding="utf-8")
        return ApplyResult(
            ok=True,
            action="php_fpm.install_pool",
            changed=not self.dry_run,
            files=[pool_file.as_posix()],
        )

    def remove_pool(self, domain: str, version: str) -> ApplyResult:
        """Remove a PHP-FPM pool config for a domain."""
        pool_file = self.pool_dir / f"{domain}.conf"
        if not self.dry_run and pool_file.exists():
            pool_file.unlink()
        return ApplyResult(
            ok=True,
            action="php_fpm.remove_pool",
            changed=not self.dry_run,
            files=[pool_file.as_posix()],
        )

    def reload(self, version: str) -> ApplyResult:
        """Restart the PHP-FPM service for a specific version."""
        service_name = f"php{version}-fpm"
        return self.service.restart(service_name)

    def status(self, version: str) -> ApplyResult:
        """Check PHP-FPM service status."""
        service_name = f"php{version}-fpm"


@dataclass(slots=True)
class PlannedDatabaseDriver:
    """Database backend scaffold (MySQL/MariaDB and PostgreSQL)."""

    service: PlannedServiceDriver
    dry_run: bool = True

    def _mysql_command(self, sql: str) -> list[str]:
        return ["mysql", "-e", sql]

    def _mysqldump_command(self, name: str) -> list[str]:
        return ["mysqldump", "--single-transaction", name]

    def _postgres_create_command(self, name: str) -> list[str]:
        return ["sudo", "-u", "postgres", "createdb", name]

    def _postgres_drop_command(self, name: str) -> list[str]:
        return ["sudo", "-u", "postgres", "dropdb", name]

    def _postgres_dump_command(self, name: str) -> list[str]:
        return ["sudo", "-u", "postgres", "pg_dump", name]

    def create(self, name: str, db_type: str = "mysql") -> ApplyResult:
        if db_type in ("mysql", "mariadb"):
            return run_command(self._mysql_command(f"CREATE DATABASE IF NOT EXISTS `{name}`"), self.dry_run)
        if db_type == "postgresql":
            return run_command(self._postgres_create_command(name), self.dry_run)
        return ApplyResult(ok=False, action="db.create", message=f"unsupported db type: {db_type}")

    def drop(self, name: str, db_type: str = "mysql") -> ApplyResult:
        if db_type in ("mysql", "mariadb"):
            return run_command(self._mysql_command(f"DROP DATABASE IF EXISTS `{name}`"), self.dry_run)
        if db_type == "postgresql":
            return run_command(self._postgres_drop_command(name), self.dry_run)
        return ApplyResult(ok=False, action="db.drop", message=f"unsupported db type: {db_type}")

    def backup(self, name: str, dest: Path, db_type: str = "mysql") -> ApplyResult:
        if db_type in ("mysql", "mariadb"):
            return run_command([*self._mysqldump_command(name), ">", str(dest)], self.dry_run)
        if db_type == "postgresql":
            return run_command([*self._postgres_dump_command(name), ">", str(dest)], self.dry_run)
        return ApplyResult(ok=False, action="db.backup", message=f"unsupported db type: {db_type}")


@dataclass(slots=True)
class PlannedSslDriver:
    """SSL certificate scaffold (Let's Encrypt via certbot)."""

    service: PlannedServiceDriver
    dry_run: bool = True

    def issue_letsencrypt(
        self,
        domain: str,
        email: str,
        *,
        staging: bool = False,
        webroot: Path | None = None,
    ) -> ApplyResult:
        command: list[str] = ["certbot", "certonly", "--non-interactive", "--agree-tos", "--email", email, "-d", domain]
        if staging:
            command += ["--staging"]
        if webroot is not None:
            command += ["--webroot", "-w", str(webroot)]
        else:
            command += ["--nginx"]
        result = run_command(command, self.dry_run)
        reload = self.service.reload(self._web_server_for(domain))
        return ApplyResult(
            ok=result.ok,
            action="ssl.issue_letsencrypt",
            changed=result.changed,
            message=result.message,
            commands=[*result.commands, *reload.commands],
        )

    def renew(self, domain: str) -> ApplyResult:
        result = run_command(["certbot", "renew", "--cert-name", domain], self.dry_run)
        reload = self.service.reload(self._web_server_for(domain))
        return ApplyResult(
            ok=result.ok,
            action="ssl.renew",
            changed=result.changed,
            message=result.message,
            commands=[*result.commands, *reload.commands],
        )

    def _web_server_for(self, domain: str) -> str:
        """Return the web server service name to reload after cert changes."""
        return "nginx"


@dataclass(slots=True)
class PlannedFirewallDriver:
    """Firewall scaffold (UFW on Linux)."""

    dry_run: bool = True

    def status(self) -> ApplyResult:
        return run_command(["ufw", "status"], self.dry_run)

    def enable(self) -> ApplyResult:
        return run_command(["ufw", "--force", "enable"], self.dry_run)

    def disable(self) -> ApplyResult:
        return run_command(["ufw", "disable"], self.dry_run)

    def allow(self, port: int, proto: str = "tcp") -> ApplyResult:
        return run_command(["ufw", "allow", f"{port}/{proto}"], self.dry_run)

    def deny(self, port: int, proto: str = "tcp") -> ApplyResult:
        return run_command(["ufw", "deny", f"{port}/{proto}"], self.dry_run)

    def list_rules(self) -> ApplyResult:
        return run_command(["ufw", "status", "numbered"], self.dry_run)
        return self.service.status(service_name)
