"""macOS production driver scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import BindDnsDriver, FileWebServerDriver, PhpFpmDriver, PlannedMailDriver, PlannedPackageDriver, PlannedServiceDriver


@dataclass(slots=True)
class MacOSDriver:
    """macOS driver using Caddy/Homebrew/launchd-friendly defaults."""

    dry_run: bool = True
    name: str = "macos"
    config_root: Path = Path("/usr/local/etc/atulya-launch")
    services: PlannedServiceDriver = field(init=False)
    packages: PlannedPackageDriver = field(init=False)
    web: FileWebServerDriver = field(init=False)
    dns: BindDnsDriver = field(init=False)
    mail: PlannedMailDriver = field(init=False)
    php_fpm: PhpFpmDriver = field(init=False)

    def __post_init__(self) -> None:
        self.services = PlannedServiceDriver("launchd", dry_run=self.dry_run)
        self.packages = PlannedPackageDriver(["brew", "install"], dry_run=self.dry_run)
        self.web = FileWebServerDriver("caddy", Path("/usr/local/etc/caddy/sites"), self.services, self.dry_run)
        self.dns = BindDnsDriver(Path("/usr/local/etc/bind/zones"), self.services, self.dry_run)
        self.mail = PlannedMailDriver(Path("/usr/local/etc/postfix"), self.services, self.dry_run)
        self.php_fpm = PhpFpmDriver(Path("/usr/local/etc/php"), self.services, self.dry_run)
