import os
import sys
import subprocess
import secrets
import string
import socket
from pathlib import Path

import yaml


CONFIG_DIR = Path.home() / ".atulya-launch"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

TEMPLATES_DIR = Path(__file__).parent / "templates"


def is_linux():
    return sys.platform.startswith("linux")


def is_macos():
    return sys.platform == "darwin"


def is_windows():
    return sys.platform == "win32"


def get_platform():
    if is_linux():
        return "linux"
    if is_macos():
        return "macos"
    if is_windows():
        return "windows"
    return sys.platform


def run_command(command, capture_output=True, check=True, timeout=60):
    if isinstance(command, str):
        command = command.split()
    try:
        result = subprocess.run(
            command,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as error:
        return error
    except FileNotFoundError:
        return None


def load_config():
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r") as file_handle:
        return yaml.safe_load(file_handle) or {}


def save_config(config_data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as file_handle:
        yaml.dump(config_data, file_handle, default_flow_style=False)


def get_config_value(key_path, default=None):
    config_data = load_config()
    keys = key_path.split(".")
    current = config_data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
    return current if current is not None else default


def set_config_value(key_path, value):
    config_data = load_config()
    keys = key_path.split(".")
    current = config_data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
    save_config(config_data)


def generate_password(length=24):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def is_port_available(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        result = sock.connect_ex((host, port))
        return result != 0


def get_service_manager():
    if is_linux():
        return "systemd"
    if is_macos():
        return "launchd"
    if is_windows():
        return "windows"
    return None


def service_action(action, service_name):
    service_manager = get_service_manager()
    if service_manager == "systemd":
        command = ["systemctl", action, service_name]
        return run_command(command)
    if service_manager == "launchd":
        plist_path = f"/Library/LaunchDaemons/{service_name}.plist"
        if action == "enable":
            return run_command(["launchctl", "load", plist_path])
        if action == "disable":
            return run_command(["launchctl", "unload", plist_path])
        if action == "start":
            return run_command(["launchctl", "start", service_name])
        if action == "stop":
            return run_command(["launchctl", "stop", service_name])
        if action == "restart":
            run_command(["launchctl", "stop", service_name])
            return run_command(["launchctl", "start", service_name])
        if action == "status":
            return run_command(["launchctl", "list", service_name])
    if service_manager == "windows":
        # Use sc.exe for Windows services
        if action in ("start", "stop", "restart"):
            cmd = ["sc.exe", action, service_name]
            return run_command(cmd)
        if action == "enable":
            # sc config <service> start= auto
            return run_command(["sc.exe", "config", service_name, "start=", "auto"])
        if action == "disable":
            # sc config <service> start= disabled
            return run_command(["sc.exe", "config", service_name, "start=", "disabled"])
        if action == "status":
            return run_command(["sc.exe", "query", service_name])
    return None


def service_exists(service_name):
    service_manager = get_service_manager()
    if service_manager == "systemd":
        result = run_command(["systemctl", "is-active", service_name], check=False)
        return result is not None and result.returncode == 0
    if service_manager == "launchd":
        # On macOS, check if service is loaded
        result = run_command(["launchctl", "list"], check=False)
        if result and result.stdout:
            # Check if service_name appears in list (simplistic)
            return service_name in result.stdout
        return False
    if service_manager == "windows":
        # Query service state
        result = run_command(["sc.exe", "query", service_name], check=False)
        if result and result.stdout:
            # Look for STATE line
            for line in result.stdout.split('\n'):
                if line.strip().startswith("STATE"):
                    # e.g., "STATE              : 4 RUNNING"
                    if "RUNNING" in line:
                        return True
                    else:
                        return False
        return False
    return False


def render_template(template_name, variables):
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        return None
    from jinja2 import Environment, FileSystemLoader
    env_loader = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env_loader.get_template(template_name)
    return template.render(**variables)


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    sites_dir = CONFIG_DIR / "sites"
    sites_dir.mkdir(exist_ok=True)
    ssl_dir = CONFIG_DIR / "ssl"
    ssl_dir.mkdir(exist_ok=True)
    backups_dir = CONFIG_DIR / "backups"
    backups_dir.mkdir(exist_ok=True)
    dbs_dir = CONFIG_DIR / "databases"
    dbs_dir.mkdir(exist_ok=True)
    users_dir = CONFIG_DIR / "users"
    users_dir.mkdir(exist_ok=True)
    ai_models_dir = CONFIG_DIR / "ai-models"
    ai_models_dir.mkdir(exist_ok=True)
    logs_dir = CONFIG_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    return CONFIG_DIR
def linux_command(command, capture_output=True, check=False, timeout=60):
    if utils.is_linux():
        return utils.run_command(command, capture_output, check, timeout)
    else:
        # Log a warning and return a mock success
        import logging
        logging.warning(f"Command {command} is Linux-only and was skipped on {utils.get_platform()}")
        # Return a mock CompletedProcess with returncode 0
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
