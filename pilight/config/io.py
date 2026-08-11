"""Load and save the main config file.

Two failure modes, handled deliberately differently:

- **Missing file** -- first run. Documented defaults are written to disk and
  returned, so the file exists immediately for the user to find and edit.
- **Corrupt or unreadable file** -- logged loudly, defaults are used *for
  this run only*, and the file on disk is left untouched. A bad config must
  never leave the room dark all night, but it also must not silently
  overwrite whatever the user had; that's still on disk to inspect or
  recover by hand.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pilight.util.atomic import atomic_write_text

from .model import PiLightConfig

log = logging.getLogger(__name__)


def load_config(path: Path) -> PiLightConfig:
    if not path.exists():
        config = PiLightConfig.defaults()
        save_config(path, config)
        log.info("no config at %s; wrote defaults", path)
        return config

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error(
            "config at %s is unreadable or corrupt (%s); using defaults for this run", path, exc
        )
        return PiLightConfig.defaults()

    if not isinstance(data, dict):
        log.error(
            "config at %s does not contain a JSON object; using defaults for this run", path
        )
        return PiLightConfig.defaults()

    return PiLightConfig.from_dict(data)


def save_config(path: Path, config: PiLightConfig) -> None:
    atomic_write_text(path, json.dumps(config.to_dict(), indent=2) + "\n")
