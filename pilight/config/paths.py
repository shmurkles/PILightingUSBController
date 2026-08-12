"""The documented default location of the main config file.

A system-wide state directory (see docs/story-7-systemd-service.md for why
/var/lib/pilight was chosen) so the root scheduler daemon and the
unprivileged GUI can agree on one path without either hardcoding the
other's home directory.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_CONFIG_PATH = Path("/var/lib/pilight/config.json")
