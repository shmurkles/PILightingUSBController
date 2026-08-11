"""Sunset time, computed locally.

astral implements the NOAA Solar Calculator's equations directly against
(latitude, longitude, date) -- no network call is possible, let alone made.
"""

from __future__ import annotations

from datetime import date as date_
from datetime import datetime
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun


class SunError(Exception):
    """Base class for every failure this module can raise."""


class PolarDayError(SunError):
    """The sun does not set (or does not rise) on this date at this latitude.

    astral raises a bare ``ValueError`` for this case; it's re-raised as this
    typed, documented exception so a caller can catch it specifically instead
    of guessing what a ``ValueError`` from deep inside astral means. There is
    no sensible datetime to return -- the caller (the Story 6 scheduler)
    decides its own fallback (e.g. treat the day as always on, or always off)
    rather than have this module invent one.
    """


def get_sunset(date: date_, lat: float, lon: float, tz: str) -> datetime:
    """Today's sunset for a location, computed with no network access.

    Args:
        date: the calendar date to compute sunset for, in the location's own
            timezone -- not UTC.
        lat: latitude in degrees, positive north.
        lon: longitude in degrees, positive east.
        tz: IANA timezone name, e.g. ``"America/Los_Angeles"``.

    Returns:
        A timezone-aware ``datetime`` in the ``tz`` timezone: the moment the
        sun's upper limb touches the horizon (civil sunset, corrected for
        atmospheric refraction -- see RESEARCH.md §3 for why this definition
        and not "fully dark"; the offset slider is what covers that gap).

    Raises:
        PolarDayError: at latitudes where the sun does not set on this date
            (astral raises the same error for "does not rise"; both mean
            there is no ordinary sunset to report).
    """
    zone = ZoneInfo(tz)
    location = LocationInfo(latitude=lat, longitude=lon, timezone=tz)
    try:
        result = sun(location.observer, date=date, tzinfo=zone)
    except ValueError as exc:
        raise PolarDayError(
            f"sun does not set on {date} at lat={lat}, lon={lon} ({tz}): {exc}"
        ) from exc
    return result["sunset"]
