"""The config schema: a frozen dataclass plus per-field sanitization.

Every field is validated independently on load. An out-of-range or malformed
value is replaced with its documented default and logged -- it never fails
the whole file. That's deliberate: one bad field must not be able to take
the rest of a working config down with it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from pilight.location import ResolvedLocation

log = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1

DEFAULT_OFFSET_MINUTES = 0
OFFSET_MIN_MINUTES = -180
OFFSET_MAX_MINUTES = 180

DEFAULT_OFF_TIME = "23:30"
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

DEFAULT_BACKEND = "uhubctl"

#: Config keys with dedicated PiLightConfig fields -- everything else that's
#: a JSON object is treated as settings for some named backend (Story 2's
#: create_backend() reads config[<backend name>]) and passed through as-is.
_RESERVED_KEYS = frozenset(
    {"schema_version", "offset_minutes", "off_time", "location", "manual_override", "backend"}
)


@dataclass(frozen=True)
class PiLightConfig:
    schema_version: int = CURRENT_SCHEMA_VERSION
    offset_minutes: int = DEFAULT_OFFSET_MINUTES
    off_time: str = DEFAULT_OFF_TIME
    location: ResolvedLocation | None = None
    manual_override: dict | None = None
    backend: str = DEFAULT_BACKEND
    #: backend name -> its settings, e.g. {"uhubctl": {"location": "2"}}.
    #: Keyed by name rather than fixed fields so a future backend (the RESEARCH.md
    #: §1 option B GPIO/relay fallback) needs no schema change here.
    backend_settings: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def defaults(cls) -> PiLightConfig:
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Serialize for disk -- also directly usable as
        ``pilight.power.create_backend(config.to_dict())``, since ``backend``
        and each backend's settings land as top-level sibling keys, exactly
        what that function expects."""
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "offset_minutes": self.offset_minutes,
            "off_time": self.off_time,
            "location": self.location.to_dict() if self.location is not None else None,
            "manual_override": self.manual_override,
            "backend": self.backend,
        }
        data.update(self.backend_settings)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PiLightConfig:
        return cls(
            schema_version=_validate_schema_version(data.get("schema_version")),
            offset_minutes=_clamp_int(
                data.get("offset_minutes", DEFAULT_OFFSET_MINUTES),
                OFFSET_MIN_MINUTES,
                OFFSET_MAX_MINUTES,
                "offset_minutes",
                DEFAULT_OFFSET_MINUTES,
            ),
            off_time=_validate_off_time(data.get("off_time", DEFAULT_OFF_TIME)),
            location=_validate_location(data.get("location")),
            manual_override=_validate_manual_override(data.get("manual_override")),
            backend=_validate_backend_name(data.get("backend", DEFAULT_BACKEND)),
            backend_settings={
                key: value
                for key, value in data.items()
                if key not in _RESERVED_KEYS and isinstance(value, dict)
            },
        )


def _validate_schema_version(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if value is not None:
        log.warning(
            "config field schema_version=%r is not an int; using %d",
            value,
            CURRENT_SCHEMA_VERSION,
        )
    return CURRENT_SCHEMA_VERSION


def _clamp_int(value: Any, lo: int, hi: int, field_name: str, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        log.warning("config field %s=%r is not a number; using default %d", field_name, value, default)
        return default
    clamped = max(lo, min(hi, number))
    if clamped != number:
        log.warning(
            "config field %s=%d is out of range [%d, %d]; clamped to %d",
            field_name,
            number,
            lo,
            hi,
            clamped,
        )
    return clamped


def _validate_off_time(value: Any) -> str:
    if isinstance(value, str) and _TIME_RE.match(value):
        return value
    log.warning("config field off_time=%r is not HH:MM; using default %r", value, DEFAULT_OFF_TIME)
    return DEFAULT_OFF_TIME


def _validate_location(value: Any) -> ResolvedLocation | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        log.warning("config field location=%r is not an object; discarding", value)
        return None
    try:
        return ResolvedLocation.from_dict(value)
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("config field location is malformed (%s); discarding", exc)
        return None


def _validate_manual_override(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        log.warning("config field manual_override=%r is not an object; discarding", value)
        return None
    # Story 10 owns this shape's own validation; here it's opaque pass-through.
    return value


def _validate_backend_name(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    log.warning("config field backend=%r is not a usable string; using default %r", value, DEFAULT_BACKEND)
    return DEFAULT_BACKEND
