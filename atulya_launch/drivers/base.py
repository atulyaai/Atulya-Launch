"""Driver contracts for OS-specific production operations.

The panel should call these interfaces instead of writing directly to
system paths such as /etc/bind, /etc/postfix, launchd, or Windows services.
Implementations may run in dry-run mode while the production integration is
being completed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class ApplyResult:
    """Result returned by a driver operation."""

    ok: bool
    action: str
    changed: bool = False
    message: str = ""
    commands: list[list[str]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BindZone:
    """DNS zone content ready to write to a backend."""

    domain: str
    records: list[dict[str, str | int]]
    serial: int


class ServiceDriver(Protocol):
    """Service manager abstraction."""

    def reload(self, service: str) -> ApplyResult:
        """Reload a service."""

    def restart(self, service: str) -> ApplyResult:
        """Restart a service."""

    def status(self, service: str) -> ApplyResult:
        """Read service status."""


class PackageDriver(Protocol):
    """Package installation abstraction."""

    def install(self, packages: list[str]) -> ApplyResult:
        """Install packages for the current platform."""


class WebServerDriver(Protocol):
    """Web server abstraction for Nginx, Caddy, and Apache-compatible targets."""

    def apply_site(self, domain: str, config: str) -> ApplyResult:
        """Write or update a site config."""

    def reload(self) -> ApplyResult:
        """Reload the web server."""


class DnsDriver(Protocol):
    """DNS backend abstraction."""

    def apply_zone(self, zone: BindZone) -> ApplyResult:
        """Write a zone and reload the DNS backend."""


class MailDriver(Protocol):
    """Mail backend abstraction."""

    def apply_domain(self, domain: str, mailboxes: list[dict[str, str | int]]) -> ApplyResult:
        """Write virtual mailbox data and reload mail services."""


class PlatformDriver(Protocol):
    """All production integrations for one platform."""

    name: str
    config_root: Path
    services: ServiceDriver
    packages: PackageDriver
    web: WebServerDriver
    dns: DnsDriver
    mail: MailDriver
