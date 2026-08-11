"""One-time IP geolocation: a single HTTPS request, never repeated after caching."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .errors import NoNetworkError

_ENDPOINT = "https://ipapi.co/json/"
_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class IPLocation:
    lat: float
    lon: float
    city: str
    country: str
    timezone: str


def geolocate_by_ip(timeout: float = _TIMEOUT_SECONDS, endpoint: str = _ENDPOINT) -> IPLocation:
    """This device's approximate location, from its public IP.

    A single HTTPS GET, per RESEARCH.md §2 -- accurate to city level
    (5-50 km), which the same section shows is far tighter than sunset
    timing needs. Called at most once per device, ever: the result is cached
    to disk, and resolve_location() only calls this again if the cache is
    empty or the user explicitly asks to re-detect.

    Raises:
        NoNetworkError: no network, a timeout, a non-2xx response, or a
            response missing the fields this needs. Callers fall back to the
            offline city picker rather than propagate this.
    """
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout) as response:  # noqa: S310
            if response.status != 200:
                raise NoNetworkError(f"{endpoint} returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NoNetworkError(f"could not reach {endpoint}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NoNetworkError(f"{endpoint} returned unparseable JSON: {exc}") from exc

    if payload.get("error"):
        raise NoNetworkError(f"{endpoint} reported an error: {payload.get('reason', payload)}")

    try:
        return IPLocation(
            lat=float(payload["latitude"]),
            lon=float(payload["longitude"]),
            city=str(payload.get("city") or ""),
            country=str(payload.get("country_name") or payload.get("country") or ""),
            timezone=str(payload["timezone"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NoNetworkError(f"{endpoint} response missing expected fields: {exc}") from exc
