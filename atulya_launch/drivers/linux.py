"""Linux production driver scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import BindDnsDriver, FileWebServerDriver, PlannedMailDriver, PlannedPackageDriver, PlannedServiceDriver


@dataclass(slots=True)
class LinuxDriver:
    """Linux driver using Nginx, BIND, Postfix, Dovecot, and systemd."""

    dry_run: bool = True
    name: str = "linux"
    config_root: Path = Path("/etc/atulya-launch")
    services: PlannedServiceDriver = field(init=False)
    packages: PlannedPackageDriver = field(init=False)
    web: FileWebServerDriver = field(init=False)
    dns: BindDnsDriver = field(init=False)
    mail: PlannedMailDriver = field(init=False)

    def __post_init__(self) -> None:
        self.services = PlannedServiceDriver("systemd", dry_run=self.dry_run)
        self.packages = PlannedPackageDriver(["apt-get", "install", "-y"], dry_run=self.dry_run)
        self.web = FileWebServerDriver("nginx", Path("/etc/nginx/sites-available"), self.services, self.dry_run)
        self.dns = BindDnsDriver(Path("/etc/bind/zones"), self.services, self.dry_run)
        self.mail = PlannedMailDriver(Path("/etc/postfix"), self.services, self.dry_run)
