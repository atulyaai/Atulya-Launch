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


@dataclass(slots=True)
class FileWebServerDriver:
    """File-backed web server scaffold."""

    name: str
    config_dir: Path
    service: PlannedServiceDriver
    dry_run: bool = True

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


@dataclass(slots=True)
class BindDnsDriver:
    """BIND zone file scaffold."""

    zone_dir: Path
    service: PlannedServiceDriver
    dry_run: bool = True

    def apply_zone(self, zone: BindZone) -> ApplyResult:
        target = self.zone_dir / f"db.{zone.domain}"
        content = self._render_zone(zone)
        if not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        reload_result = self.service.reload("bind9")
        return ApplyResult(
            ok=reload_result.ok,
            action="bind.apply_zone",
            changed=not self.dry_run,
            commands=reload_result.commands,
            files=[target.as_posix()],
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


@dataclass(slots=True)
class PlannedMailDriver:
    """Postfix/Dovecot mailbox scaffold."""

    config_dir: Path
    service: PlannedServiceDriver
    dry_run: bool = True

    def apply_domain(self, domain: str, mailboxes: list[dict[str, str | int]]) -> ApplyResult:
        target = self.config_dir / "virtual_mailboxes"
        lines = [f"{box.get('mailbox')}@{domain} {domain}/{box.get('mailbox')}/" for box in mailboxes]
        if not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        postfix = self.service.reload("postfix")
        dovecot = self.service.reload("dovecot")
        return ApplyResult(
            ok=postfix.ok and dovecot.ok,
            action="mail.apply_domain",
            changed=not self.dry_run,
            commands=[*postfix.commands, *dovecot.commands],
            files=[target.as_posix()],
        )
