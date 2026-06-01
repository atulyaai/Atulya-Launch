"""Linux production driver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import (
    BindDnsDriver,
    FileWebServerDriver,
    PhpFpmDriver,
    PlannedDatabaseDriver,
    PlannedFirewallDriver,
    PlannedMailDriver,
    PlannedPackageDriver,
    PlannedServiceDriver,
    PlannedSslDriver,
    detect_package_manager,
)


@dataclass(slots=True)
class LinuxDriver:
    """Linux driver using Nginx, BIND, Postfix, Dovecot, UFW, certbot, and systemd."""

    dry_run: bool = True
    name: str = "linux"
    config_root: Path = Path("/etc/atulya-launch")
    services: PlannedServiceDriver = field(init=False)
    packages: PlannedPackageDriver = field(init=False)
    web: FileWebServerDriver = field(init=False)
    dns: BindDnsDriver = field(init=False)
    mail: PlannedMailDriver = field(init=False)
    php_fpm: PhpFpmDriver = field(init=False)
    databases: PlannedDatabaseDriver = field(init=False)
    ssl: PlannedSslDriver = field(init=False)
    firewall: PlannedFirewallDriver = field(init=False)

    def __post_init__(self) -> None:
        self.services = PlannedServiceDriver("systemd", dry_run=self.dry_run)
        pkg_cmd, _ = detect_package_manager()
        self.packages = PlannedPackageDriver(pkg_cmd, dry_run=self.dry_run)
        self.web = FileWebServerDriver("nginx", Path("/etc/nginx/sites-available"), self.services, self.dry_run)
        self.dns = BindDnsDriver(Path("/etc/bind/zones"), self.services, self.dry_run)
        self.mail = PlannedMailDriver(Path("/etc/postfix"), self.services, self.dry_run)
        self.php_fpm = PhpFpmDriver(Path("/etc/php"), self.services, self.dry_run)
        self.databases = PlannedDatabaseDriver(self.services, self.dry_run)
        self.ssl = PlannedSslDriver(self.services, self.dry_run)
        self.firewall = PlannedFirewallDriver(self.dry_run)
