"""Timezone resolution: system settings first, then IP result, then the city record.

DST itself needs no special handling here -- see RESEARCH.md §4: computing in
timezone-aware local time via ``zoneinfo`` (as pilight.sun does) makes DST
jumps a non-event. This module only picks *which* IANA zone name to hand
that machinery.
"""

from __future__ import annotations

from pathlib import Path

from .errors import TimezoneUnavailableError

_ETC_TIMEZONE = Path("/etc/timezone")
_ETC_LOCALTIME = Path("/etc/localtime")
_ZONEINFO_ROOT = Path("/usr/share/zoneinfo")


def read_system_timezone() -> str | None:
    """The Pi's own configured timezone, or ``None`` if it can't be determined.

    Tries ``/etc/timezone`` first (a plain IANA name on Debian / Raspberry Pi
    OS), then falls back to resolving the ``/etc/localtime`` symlink against
    ``/usr/share/zoneinfo``. Neither touches the network -- this is what
    keeps ``resolve_timezone`` network-free even on the "IP result" and
    "city record" branches, which only ever supply a fallback string that
    was already resolved by an earlier network call or the bundled database.
    """
    try:
        name = _ETC_TIMEZONE.read_text(encoding="utf-8").strip()
        if name:
            return name
    except OSError:
        pass

    try:
        target = _ETC_LOCALTIME.resolve()
        return str(target.relative_to(_ZONEINFO_ROOT))
    except (OSError, ValueError):
        return None


def resolve_timezone(
    ip_timezone: str | None = None,
    city_timezone: str | None = None,
    *,
    system_timezone: str | None | object = ...,
) -> str:
    """The timezone to use, in system-settings-first priority order.

    Args:
        ip_timezone: the timezone an IP geolocation call returned this run,
            if one was made.
        city_timezone: the timezone recorded against the chosen city, if the
            location came from a manual pick, the offline picker, or a cache
            entry whose original source was one of those.
        system_timezone: override :func:`read_system_timezone` (tests only).
            The default sentinel means "call it for real"; pass ``None``
            explicitly to simulate it being unreadable.

    Raises:
        TimezoneUnavailableError: none of the three sources produced anything.
    """
    system_tz = read_system_timezone() if system_timezone is ... else system_timezone
    for candidate in (system_tz, ip_timezone, city_timezone):
        if candidate:
            return candidate
    raise TimezoneUnavailableError(
        "could not determine a timezone from system settings, IP lookup, or city record"
    )
