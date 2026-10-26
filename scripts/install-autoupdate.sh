#!/bin/sh
# Installs the automatic updates (scripts/autoupdate.py: new Chromium, new
# Hivey AI sidebar, dev builds of main) as a systemd timer on the build host.
# Run as root, once.
#
#   sudo scripts/install-autoupdate.sh [path to the automation clone]
#
# The timer checks every 5 minutes: a check is a few GitHub API calls, and a
# build starts only when something changed, so a sidebar or Chromium update is
# picked up within minutes. The service runs the script from the automation
# clone (default ../hivey-browser-auto, also its work tree), reset to
# origin/main first, so merged changes to the automation apply by themselves.
# It runs at the lowest CPU and I/O priority; hb.py additionally caps the
# build's memory, so production services on the same host keep priority.
set -eu
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
AUTO_DIR=${1:-$(dirname "$ROOT_DIR")/hivey-browser-auto}
PYTHON=$(command -v python3)
GIT=$(command -v git)
[ -d "$AUTO_DIR/.git" ] || gh repo clone FlorianMartins/hivey-browser "$AUTO_DIR"
AUTO_DIR=$(cd "$AUTO_DIR" && pwd)

cat > /etc/systemd/system/hivey-autoupdate.service <<EOF
[Unit]
Description=Hivey Browser: automatic Chromium and Hivey AI update and release
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$(id -un)
Environment=HOME=$HOME
Environment=XWIN_ACCEPT_LICENSE=1
ExecStartPre=$GIT -C $AUTO_DIR fetch -q --prune origin
ExecStartPre=$GIT -C $AUTO_DIR checkout -q -B main origin/main
ExecStartPre=$GIT -C $AUTO_DIR reset -q --hard origin/main
ExecStart=$PYTHON $AUTO_DIR/scripts/autoupdate.py
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=infinity
EOF

cat > /etc/systemd/system/hivey-autoupdate.timer <<EOF
[Unit]
Description=Check for a new Chromium or Hivey AI sidebar every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now hivey-autoupdate.timer
systemctl list-timers hivey-autoupdate.timer --no-pager
