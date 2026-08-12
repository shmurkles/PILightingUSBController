"""The main pilight configuration file -- Story 5.

    from pathlib import Path
    from pilight.config import load_config, save_config

    config = load_config(Path("/var/lib/pilight/config.json"))
    config.offset_minutes  # -180..180, clamped on load
    config.to_dict()       # directly usable as pilight.power.create_backend(config.to_dict())

One JSON file, read by the scheduler daemon and written by the GUI (Story 9).
Malformed input is sanitized field-by-field with a logged warning rather than
rejecting the whole file -- see model.py -- because a bad config must never
leave the room dark all night.
"""

from .io import load_config, save_config
from .model import (
    CURRENT_SCHEMA_VERSION,
    DEFAULT_BACKEND,
    DEFAULT_OFF_TIME,
    DEFAULT_OFFSET_MINUTES,
    OFFSET_MAX_MINUTES,
    OFFSET_MIN_MINUTES,
    PiLightConfig,
)
from .paths import DEFAULT_CONFIG_PATH

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DEFAULT_BACKEND",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_OFF_TIME",
    "DEFAULT_OFFSET_MINUTES",
    "OFFSET_MAX_MINUTES",
    "OFFSET_MIN_MINUTES",
    "PiLightConfig",
    "load_config",
    "save_config",
]
