#!/bin/sh
# Installs the daily automatic Chromium update (scripts/autoupdate.py) as a
# systemd timer on the build host. Run as root, once.
#
#   sudo scripts/install-autoupdate.sh [path to a clone that stays in place]
#
# The service runs at the lowest CPU and I/O priority; hb.py additionally caps
# the build's memory, so production services on the same host keep priority.
set -eu
REPO_DIR=$(cd "${1:-$(dirname "$0")/..}" && pwd)
PYTHON=$(command -v python3)

cat > /etc/systemd/system/hivey-autoupdate.service <<EOF
[Unit]
Description=Hivey Browser: automatic Chromium update and release
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$(id -un)
Environment=HOME=$HOME
Environment=XWIN_ACCEPT_LICENSE=1
ExecStart=$PYTHON $REPO_DIR/scripts/autoupdate.py
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=infinity
EOF

cat > /etc/systemd/system/hivey-autoupdate.timer <<EOF
[Unit]
Description=Daily check for a new Chromium release for Hivey Browser

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now hivey-autoupdate.timer
systemctl list-timers hivey-autoupdate.timer --no-pager
