#!/bin/bash
# Push code changes from the laptop to the Mac mini and restart Launchpad there.
# Run from the Launchpad folder in Git Bash (or VS Code's terminal set to Git Bash):
#   bash deploy/deploy.sh
#
# Copies the code only. It never touches the Mac's data/ folder (database, backups,
# uploads) or its .env, so your real data and settings there stay as they are.
set -euo pipefail
cd "$(dirname "$0")/.."
# The ssh name of your Mac (an alias in ~/.ssh/config). Override: LAUNCHPAD_SSH=my-mac bash deploy/deploy.sh
MAC="${LAUNCHPAD_SSH:-macmini}"

echo "Copying code to $MAC…"
tar czf - --exclude=.venv --exclude=data --exclude=.env --exclude=.git --exclude=__pycache__ --exclude=.claude . \
  | ssh "$MAC" 'mkdir -p ~/launchpad && tar xzf - -C ~/launchpad'

echo "Installing packages and restarting…"
ssh "$MAC" 'cd ~/launchpad && .venv/bin/python -m pip install --quiet -r requirements.txt \
  && launchctl kickstart -k "gui/$(id -u)/com.launchpad.app" \
  && for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do sleep 1; \
       code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5050/login); [ "$code" = "200" ] || [ "$code" = "302" ] && break; done; \
     echo "Launchpad answered HTTP $code after ${i}s"'
