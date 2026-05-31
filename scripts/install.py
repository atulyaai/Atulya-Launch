#!/usr/bin/env python3
"""
Cross-platform Atulya Launch bootstrapper.

This script is intentionally stdlib-only so it can be run directly from curl,
PowerShell, or a local checkout.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/atulyaai/Atulya-Launch/archive/refs/heads/main.zip"


def run(command, *, check=True):
    print("+ " + " ".join(str(part) for part in command))
    return subprocess.run(command, check=check)


def default_prefix():
    system = platform.system().lower()
    if system == "windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Atulya" / "Launch"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "Atulya" / "Launch"
    return Path.home() / ".atulya-launch"


def venv_python(venv_dir):
    if platform.system().lower() == "windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def venv_executable(venv_dir, name):
    if platform.system().lower() == "windows":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def detect_source(args):
    cwd = Path.cwd()
    if args.local:
        return str(cwd)
    if (cwd / "pyproject.toml").exists() and (cwd / "atulya_launch").exists():
        return str(cwd)
    extra = "[all]" if args.all else ""
    return f"atulya-launch{extra} @ {args.repo}"


def write_launchers(prefix, venv_dir, panel_home, host, port):
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    python = venv_python(venv_dir)

    if platform.system().lower() == "windows":
        cli = bin_dir / "atulya-launch.cmd"
        cli.write_text(
            f"@echo off\r\nset ATULYA_HOME={panel_home}\r\n\"{python}\" -m atulya_launch %*\r\n",
            encoding="utf-8",
        )
        server = bin_dir / "atulya-launch-serve.cmd"
        server.write_text(
            f"@echo off\r\nset ATULYA_HOME={panel_home}\r\n\"{python}\" -m atulya_launch serve --host {host} --port {port}\r\n",
            encoding="utf-8",
        )
    else:
        cli = bin_dir / "atulya-launch"
        cli.write_text(
            f"#!/usr/bin/env sh\nexport ATULYA_HOME=\"{panel_home}\"\nexec \"{python}\" -m atulya_launch \"$@\"\n",
            encoding="utf-8",
        )
        cli.chmod(0o755)
        server = bin_dir / "atulya-launch-serve"
        server.write_text(
            f"#!/usr/bin/env sh\nexport ATULYA_HOME=\"{panel_home}\"\nexec \"{python}\" -m atulya_launch serve --host {host} --port {port}\n",
            encoding="utf-8",
        )
        server.chmod(0o755)

    return bin_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install Atulya Launch on Linux, macOS, or Windows.")
    parser.add_argument("--prefix", type=Path, default=default_prefix(), help="Install directory")
    parser.add_argument("--home", type=Path, default=None, help="ATULYA_HOME data directory")
    parser.add_argument("--repo", default=REPO_URL, help="Package URL to install from")
    parser.add_argument("--local", action="store_true", help="Install from the current checkout")
    parser.add_argument("--all", action="store_true", help="Install package with [all] extras")
    parser.add_argument("--admin", default="admin", help="Initial admin username")
    parser.add_argument("--password", default=None, help="Initial admin password; generated if omitted")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind host for generated launcher")
    parser.add_argument("--port", default="8080", help="Dashboard bind port for generated launcher")
    parser.add_argument("--no-init", action="store_true", help="Install only; do not initialize config")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without changing files")
    args = parser.parse_args(argv)

    prefix = args.prefix.expanduser().resolve()
    panel_home = (args.home or (prefix / "data")).expanduser().resolve()
    venv_dir = prefix / "venv"
    source = detect_source(args)

    print(f"Atulya Launch installer")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Install:  {prefix}")
    print(f"Data:     {panel_home}")
    print(f"Source:   {source}")

    if args.dry_run:
        print("Dry run complete.")
        return 0

    prefix.mkdir(parents=True, exist_ok=True)
    panel_home.mkdir(parents=True, exist_ok=True)

    if not venv_python(venv_dir).exists():
        run([sys.executable, "-m", "venv", str(venv_dir)])

    python = venv_python(venv_dir)
    run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(python), "-m", "pip", "install", "--upgrade", source])

    env = os.environ.copy()
    env["ATULYA_HOME"] = str(panel_home)
    if not args.no_init:
        command = [str(python), "-m", "atulya_launch", "init", "--admin", args.admin, "--rotate-token"]
        if args.password:
            command.extend(["--password", args.password])
        print("+ " + " ".join(command))
        subprocess.run(command, check=True, env=env)

    bin_dir = write_launchers(prefix, venv_dir, panel_home, args.host, args.port)
    cli = venv_executable(venv_dir, "atulya-launch")

    print("")
    print("Atulya Launch installed.")
    print(f"CLI:       {cli}")
    print(f"Launchers: {bin_dir}")
    print(f"Data:      {panel_home}")
    print("")
    print("Try:")
    if platform.system().lower() == "windows":
        print(f"  {bin_dir}\\atulya-launch.cmd system")
        print(f"  {bin_dir}\\atulya-launch-serve.cmd")
    else:
        print(f"  {bin_dir}/atulya-launch system")
        print(f"  {bin_dir}/atulya-launch-serve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
