#!/usr/bin/env python3
"""Atulya Launch - Cross-Platform Installer

Detects OS and installs all required services:
- Ubuntu/Debian: apt, nginx, mysql, php-fpm, certbot, ufw, fail2ban
- CentOS/RHEL/Rocky: dnf/yum, nginx, mariadb, php-fpm, certbot, firewalld
- Arch Linux: pacman, nginx, mariadb, php-fpm, certbot, iptables-nft
- macOS: brew, caddy, mariadb, php, certbot
- Windows: choco/winget, caddy, mysql, php

Usage:
  Linux/macOS: sudo python3 install.py
  Windows: python install.py (as Administrator)
  Dry run: python3 install.py --dry-run --local
"""

import os
import sys
import subprocess
import platform
import shutil
import secrets
import string
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv
LOCAL_MODE = "--local" in sys.argv

PANEL_HOST = os.environ.get("PANEL_HOST", "127.0.0.1")
PANEL_PORT = os.environ.get("PANEL_PORT", "8080")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
SKIP_DOCKER = os.environ.get("SKIP_DOCKER", "0") == "1"

def log(msg):
    print(f"\033[1;32m[Atulya]\033[0m {msg}")

def warn(msg):
    print(f"\033[1;33m[Warning]\033[0m {msg}")

def err(msg):
    print(f"\033[1;31m[Error]\033[0m {msg}", file=sys.stderr)
    sys.exit(1)

def run(cmd, check=False, shell=False):
    if DRY_RUN:
        log(f"[dry-run] Would run: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    log(f"Running: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=check, shell=shell)
    if result.returncode != 0 and check:
        err(f"Command failed: {result.stderr}")
    return result

def generate_password(length=24):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def detect_os():
    system = platform.system().lower()
    if system == "linux":
        try:
            with open("/etc/os-release") as f:
                info = f.read().lower()
            if "ubuntu" in info or "debian" in info:
                return "debian"
            elif "centos" in info or "rhel" in info or "rocky" in info or "almalinux" in info:
                return "rhel"
            elif "fedora" in info:
                return "fedora"
            elif "arch" in info or "manjaro" in info:
                return "arch"
        except FileNotFoundError:
            pass
        return "linux_unknown"
    elif system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    return "unknown"

def detect_package_manager(os_type):
    if os_type == "debian":
        return "apt"
    elif os_type in ("rhel", "fedora"):
        if shutil.which("dnf"):
            return "dnf"
        return "yum"
    elif os_type == "arch":
        return "pacman"
    elif os_type == "macos":
        return "brew"
    elif os_type == "windows":
        if shutil.which("choco"):
            return "choco"
        if shutil.which("winget"):
            return "winget"
    return None

def install_package(pkg_name, pkg_mgr=None):
    if pkg_mgr is None:
        pkg_mgr = detect_package_manager(detect_os())
    if pkg_mgr == "apt":
        run(["apt-get", "install", "-y", pkg_name])
    elif pkg_mgr == "dnf":
        run(["dnf", "install", "-y", pkg_name])
    elif pkg_mgr == "yum":
        run(["yum", "install", "-y", pkg_name])
    elif pkg_mgr == "pacman":
        run(["pacman", "-S", "--noconfirm", pkg_name])
    elif pkg_mgr == "brew":
        run(["brew", "install", pkg_name])
    elif pkg_mgr == "choco":
        run(["choco", "install", pkg_name, "-y"])

def install_prerequisites(os_type):
    log("Installing prerequisites...")
    pkg_mgr = detect_package_manager(os_type)
    if pkg_mgr == "apt":
        run(["apt-get", "update", "-qq"])
        run(["apt-get", "install", "-y", "curl", "git", "python3", "python3-pip", "python3-venv", "sqlite3", "certbot", "ufw", "fail2ban"])
    elif pkg_mgr in ("dnf", "yum"):
        run([pkg_mgr, "install", "-y", "curl", "git", "python3", "python3-pip", "sqlite", "certbot", "firewalld"])
    elif pkg_mgr == "pacman":
        run(["pacman", "-S", "--noconfirm", "curl", "git", "python", "python-pip", "sqlite", "certbot"])
    elif pkg_mgr == "brew":
        run(["brew", "install", "curl", "git", "python3", "sqlite", "certbot"])
    elif pkg_mgr == "choco":
        run(["choco", "install", "git", "python3", "sqlite", "-y"])

def install_services(os_type):
    log("Installing services (Nginx, MySQL, PHP)...")
    pkg_mgr = detect_package_manager(os_type)
    if pkg_mgr == "apt":
        run(["apt-get", "install", "-y", "nginx", "mysql-server", "php-fpm", "php-mysql", "php-xml", "php-mbstring"])
    elif pkg_mgr in ("dnf", "yum"):
        run([pkg_mgr, "install", "-y", "nginx", "mariadb-server", "php-fpm", "php-mysqlnd", "php-xml", "php-mbstring"])
    elif pkg_mgr == "pacman":
        run(["pacman", "-S", "--noconfirm", "nginx", "mariadb", "php-fpm", "php-gd"])
    elif pkg_mgr == "brew":
        run(["brew", "install", "nginx", "mariadb", "php"])
    elif pkg_mgr == "choco":
        run(["choco", "install", "nginx", "mysql", "php", "-y"])

def install_docker(os_type):
    if SKIP_DOCKER:
        return
    log("Installing Docker...")
    pkg_mgr = detect_package_manager(os_type)
    if pkg_mgr == "apt":
        run(["curl", "-fsSL", "https://get.docker.com", "-o", "/tmp/get-docker.sh"])
        run(["sh", "/tmp/get-docker.sh"])
    elif pkg_mgr in ("dnf", "yum"):
        run(["curl", "-fsSL", "https://get.docker.com", "-o", "/tmp/get-docker.sh"])
        run(["sh", "/tmp/get-docker.sh"])
    elif pkg_mgr == "brew":
        run(["brew", "install", "--cask", "docker"])

def setup_panel():
    global ADMIN_PASS
    log("Setting up Atulya Launch panel...")
    panel_dir = Path("/opt/atulya-launch") if sys.platform != "win32" else Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Atulya" / "Launch"
    if DRY_RUN:
        log(f"[dry-run] Would create panel directory: {panel_dir}")
    else:
        panel_dir.mkdir(parents=True, exist_ok=True)

    # Locate the source tree (parent of scripts/ where this file lives) so we
    # can `pip install` the panel into the same Python interpreter the
    # systemd service will use. Without this, the service crashes with
    # "No module named atulya_launch" on first start.
    script_dir = Path(__file__).resolve().parent
    source_root = script_dir.parent
    pyproject = source_root / "pyproject.toml"
    if pyproject.is_file():
        log(f"Installing panel package from {source_root}...")
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=False)
        run([sys.executable, "-m", "pip", "install", "-e", str(source_root)])
    else:
        warn(f"No pyproject.toml found at {pyproject}; skipping pip install. The systemd unit WILL fail to start.")

    if not ADMIN_PASS:
        ADMIN_PASS = generate_password()
        log(f"Generated admin password: {ADMIN_PASS}")
    env_file = panel_dir / ".env"
    env_content = f"""PANEL_HOST={PANEL_HOST}
PANEL_PORT={PANEL_PORT}
ADMIN_USER={ADMIN_USER}
ADMIN_PASS={ADMIN_PASS}
ATULYA_PRODUCTION=1
"""
    if DRY_RUN:
        log(f"[dry-run] Would write environment file to {env_file}")
    else:
        env_file.write_text(env_content)
    log(f"Environment file written to {env_file}")

def setup_systemd():
    if sys.platform == "win32":
        log("[skip] systemd not available on Windows")
        return
    log("Setting up systemd service...")
    service_content = f"""[Unit]
Description=Atulya Launch Hosting Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/atulya-launch
ExecStart={sys.executable} -m atulya_launch serve --host {PANEL_HOST} --port {PANEL_PORT}
Restart=always
RestartSec=5
Environment=ATULYA_PRODUCTION=1

[Install]
WantedBy=multi-user.target
"""
    service_path = Path("/etc/systemd/system/atulya-launch.service")
    if DRY_RUN:
        log(f"[dry-run] Would write systemd service to {service_path}")
    else:
        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text(service_content)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", "atulya-launch"])
        run(["systemctl", "start", "atulya-launch"])

def setup_firewall(os_type):
    if sys.platform == "win32":
        log("[skip] Use Windows Firewall for port configuration")
        return
    log("Configuring firewall...")
    pkg_mgr = detect_package_manager(os_type)
    if pkg_mgr == "apt":
        run(["ufw", "allow", "22/tcp"])
        run(["ufw", "allow", "80/tcp"])
        run(["ufw", "allow", "443/tcp"])
        run(["ufw", "allow", PANEL_PORT + "/tcp"])
        run(["ufw", "--force", "enable"])
    elif pkg_mgr in ("dnf", "yum"):
        run(["firewall-cmd", "--permanent", "--add-port=22/tcp"])
        run(["firewall-cmd", "--permanent", "--add-port=80/tcp"])
        run(["firewall-cmd", "--permanent", "--add-port=443/tcp"])
        run(["firewall-cmd", "--permanent", f"--add-port={PANEL_PORT}/tcp"])
        run(["firewall-cmd", "--reload"])

def main():
    os_type = detect_os()
    log(f"Detected OS: {os_type} ({platform.platform()})")
    if os_type == "unknown":
        err("Unsupported operating system")
    install_prerequisites(os_type)
    install_services(os_type)
    install_docker(os_type)
    setup_panel()
    setup_systemd()
    setup_firewall(os_type)
    if DRY_RUN:
        log("=" * 60)
        log("Dry run complete.")
        log(f"Would install panel at: http://{PANEL_HOST}:{PANEL_PORT}")
        log(f"Would use admin password: {ADMIN_PASS}")
        log("=" * 60)
    else:
        log("=" * 60)
        log("Installation complete!")
        log(f"Panel URL: http://{PANEL_HOST}:{PANEL_PORT}")
        log(f"Admin user: {ADMIN_USER}")
        log(f"Admin password: {ADMIN_PASS}")
        log("=" * 60)
        log("Start the panel: systemctl start atulya-launch")

if __name__ == "__main__":
    main()
