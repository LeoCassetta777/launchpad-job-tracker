#!/bin/bash
# One-time setup ON THE MAC MINI (run from ~/launchpad after the files are copied there):
#   bash deploy/setup_mac.sh
# Creates the Python environment, installs packages, and installs + starts the launchd agent.
# Safe to run again: it rebuilds what's needed and restarts the app.
set -euo pipefail
cd "$HOME/launchpad"

PY=/usr/local/bin/python3.13           # Homebrew Python 3.13 on this Mac
[ -x "$PY" ] || PY="$(command -v python3)"
echo "Using $PY ($("$PY" --version))"

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
mkdir -p data

PLIST="$HOME/Library/LaunchAgents/com.launchpad.app.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__HOME__|$HOME|g" deploy/com.launchpad.app.plist > "$PLIST"

# (Re)load the agent in this user's GUI session, then make sure it's running.
launchctl bootout "gui/$(id -u)/com.launchpad.app" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.launchpad.app"
sleep 3
launchctl print "gui/$(id -u)/com.launchpad.app" | grep -E "state =|pid =" || true
curl -s -o /dev/null -w "Launchpad answered HTTP %{http_code} on 127.0.0.1:5050\n" http://127.0.0.1:5050/ || echo "Not answering yet; see data/launchpad.log"
