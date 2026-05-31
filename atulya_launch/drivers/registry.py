"""Platform driver selection."""

from __future__ import annotations

import sys
from typing import Any

from .linux import LinuxDriver
from .macos import MacOSDriver
from .windows import WindowsDriver


def get_platform_driver(platform_name: str | None = None, dry_run: bool = True) -> Any:
    """Return the driver for the requested or current platform."""
    platform_name = platform_name or sys.platform
    if platform_name.startswith("linux"):
        return LinuxDriver(dry_run=dry_run)
    if platform_name == "darwin" or platform_name == "macos":
        return MacOSDriver(dry_run=dry_run)
    if platform_name in {"win32", "windows"}:
        return WindowsDriver(dry_run=dry_run)
    raise ValueError(f"unsupported platform: {platform_name}")
