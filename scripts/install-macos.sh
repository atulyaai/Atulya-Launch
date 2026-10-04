#!/usr/bin/env bash
# Atulya Launch installer for macOS 14+ (Homebrew + Caddy + launchd).
set -euo pipefail

[ "$(uname -s)" = "Darwin" ] || { echo "This script is for macOS only." >&2; exit 1; }
command -v brew >/dev/null 2>&1 || { echo "Homebrew is required: https://brew.sh" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="${ATULYA_PREFIX:-$HOME/Library/Application Support/Atulya-Launch}"
PLIST="$HOME/Library/LaunchAgents/com.atulya.launch.plist"
PORT="${ATULYA_PORT:-8443}"

brew install python@3.11 caddy redis postgresql@16 nginx
mkdir -p "$PREFIX" "$(dirname "$PLIST")"

python3.11 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --upgrade pip
"$PREFIX/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
"$PREFIX/venv/bin/pip" install -e "$REPO_DIR"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.atulya.launch</string>
  <key>ProgramArguments</key><array>
    <string>$PREFIX/venv/bin/python</string><string>-m</string><string>uvicorn</string>
    <string>atulya_launch.web.app:create_app</string><string>--factory</string>
    <string>--host</string><string>127.0.0.1</string><string>--port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO_DIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$PREFIX/panel.log</string>
  <key>StandardErrorPath</key><string>$PREFIX/panel.err</string>
</dict></plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
osascript -e 'display notification "Panel running" with title "Atulya Launch"' || true
echo "Atulya Launch is running at http://127.0.0.1:$PORT (logs: $PREFIX/panel.log)"
