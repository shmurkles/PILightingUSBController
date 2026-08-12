#!/usr/bin/env bash
#
# One-shot setup for a fresh Raspberry Pi OS install: system dependencies,
# the dedicated venv, the state directory, the systemd service, first-run
# location seeding, and a desktop launcher for the configuration window.
#
# Usage:  sudo ./scripts/install.sh
#
# Idempotent: safe to re-run (e.g. after `git pull`) to pick up updates --
# it reinstalls into the same venv and restarts the service rather than
# erroring on things that already exist.
#
set -euo pipefail

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die() {
	printf '\033[31m%s\033[0m\n' "$*" >&2
	exit 1
}

[ "$(id -u)" -eq 0 ] || die "Run with sudo: sudo $0"

REAL_USER="${SUDO_USER:-$(logname)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT=/opt/pilight
STATE_DIR=/var/lib/pilight

say "Installing system dependencies (uhubctl, python3-venv, python3-tk)..."
apt-get update -qq
apt-get install -y -qq uhubctl python3-venv python3-tk

say "Setting up $INSTALL_ROOT..."
mkdir -p "$INSTALL_ROOT"
[ -d "$INSTALL_ROOT/venv" ] || python3 -m venv "$INSTALL_ROOT/venv"
"$INSTALL_ROOT/venv/bin/pip" install -q --upgrade pip
"$INSTALL_ROOT/venv/bin/pip" install -q "$REPO_ROOT"

say "Setting up the $STATE_DIR state directory..."
groupadd -f pilight
usermod -aG pilight "$REAL_USER"
mkdir -p "$STATE_DIR"
chown root:pilight "$STATE_DIR"
chmod 2775 "$STATE_DIR"

CONFIG_PATH="$STATE_DIR/config.json"
if "$INSTALL_ROOT/venv/bin/python" -c "
from pathlib import Path
from pilight.config import load_config
raise SystemExit(0 if load_config(Path('$CONFIG_PATH')).location else 1)
" 2>/dev/null; then
	say "Location already resolved; skipping."
	echo "To change it: sudo $INSTALL_ROOT/venv/bin/python -m pilight.location resolve --redetect $CONFIG_PATH"
else
	say "Resolving this device's location (one-time, needs network)..."
	"$INSTALL_ROOT/venv/bin/python" -m pilight.location resolve "$CONFIG_PATH"
fi

say "Installing the systemd service..."
cp "$REPO_ROOT/deploy/pilight-scheduler.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pilight-scheduler

say "Installing the desktop launcher for $REAL_USER..."
USER_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
for DEST in "$USER_HOME/Desktop" "$USER_HOME/.local/share/applications"; do
	install -d -o "$REAL_USER" -g "$REAL_USER" "$DEST"
	install -m 755 -o "$REAL_USER" -g "$REAL_USER" \
		"$REPO_ROOT/deploy/pilight-gui.desktop" "$DEST/pilight-gui.desktop"
done

say "Done."
echo "Service status: sudo systemctl status pilight-scheduler"
echo "Logs:           journalctl -u pilight-scheduler -f"
echo "GUI:            the new 'Bedroom Light' desktop icon, or $INSTALL_ROOT/venv/bin/python -m pilight.gui"
echo
warn "Log out and back in (or reboot) for '$REAL_USER' to pick up the new 'pilight' group -- needed before the configuration window can save changes."
