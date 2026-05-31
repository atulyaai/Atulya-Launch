"""Windows production driver scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import BindDnsDriver, FileWebServerDriver, PhpFpmDriver, PlannedMailDriver, PlannedPackageDriver, PlannedServiceDriver


@dataclass(slots=True)
class WindowsDriver:
    """Windows driver using Caddy and service-control friendly defaults."""

    dry_run: bool = True
    name: str = "windows"
    config_root: Path = Path("C:/ProgramData/Atulya/Launch")
    services: PlannedServiceDriver = field(init=False)
    packages: PlannedPackageDriver = field(init=False)
    web: FileWebServerDriver = field(init=False)
    dns: BindDnsDriver = field(init=False)
    mail: PlannedMailDriver = field(init=False)
    php_fpm: PhpFpmDriver = field(init=False)

    def __post_init__(self) -> None:
        self.services = PlannedServiceDriver("windows", dry_run=self.dry_run)
        self.packages = PlannedPackageDriver(["winget", "install"], dry_run=self.dry_run)
        self.web = FileWebServerDriver("caddy", self.config_root / "caddy" / "sites", self.services, self.dry_run)
        self.dns = BindDnsDriver(self.config_root / "bind" / "zones", self.services, self.dry_run)
        self.mail = PlannedMailDriver(self.config_root / "mail", self.services, self.dry_run)
        self.php_fpm = PhpFpmDriver(self.config_root / "php", self.services, self.dry_run)
