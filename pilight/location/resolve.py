"""resolve_location(): the priority order that ties the rest of this package together.

manual override -> cached value -> IP geolocation (once) -> offline city picker.
See RESEARCH.md §2 for why this order.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

from .cache import load_cached_location, save_cached_location
from .citydb import CityRecord, load_city_database
from .errors import NoLocationAvailableError, NoNetworkError
from .ipgeo import IPLocation, geolocate_by_ip
from .model import LocationSource, ResolvedLocation
from .timezone import resolve_timezone

CityPicker = Callable[[Sequence[CityRecord]], CityRecord]


def _from_city(city: CityRecord, source: LocationSource) -> ResolvedLocation:
    return ResolvedLocation(
        lat=city.lat,
        lon=city.lon,
        city=city.name,
        country=city.country,
        timezone=city.timezone,
        source=source,
    )


def _with_resolved_timezone(
    location: ResolvedLocation, *, ip_timezone: str | None, city_timezone: str | None
) -> ResolvedLocation:
    tz = resolve_timezone(ip_timezone=ip_timezone, city_timezone=city_timezone)
    return replace(location, timezone=tz)


def resolve_location(
    cache_path: Path,
    *,
    manual: CityRecord | None = None,
    picker: CityPicker | None = None,
    force_redetect: bool = False,
    ip_lookup: Callable[[], IPLocation] = geolocate_by_ip,
    cities: Sequence[CityRecord] | None = None,
) -> ResolvedLocation:
    """Resolve where this device is, doing the least work necessary.

    Args:
        cache_path: where the resolved location is persisted. Read first
            (unless overridden below) and written to at the end of every
            successful call, including cache hits -- see the module
            docstring on why a cache hit still re-checks the system
            timezone.
        manual: a user-picked city that always wins and always overwrites
            the cache, per Story 4's "manual selection always overrides
            detection" criterion.
        picker: called with the full city list if there's no cache, no
            manual override, and IP geolocation failed -- the GUI supplies
            an interactive picker; tests supply a fake one. If ``None`` in
            that situation, :class:`NoLocationAvailableError` is raised
            instead of guessing.
        force_redetect: skip the cache and re-run IP geolocation (or the
            picker) even if a cached value exists. Set when the user
            explicitly asks to re-detect. This includes a previously cached
            *manual* pick -- ``force_redetect`` without also passing
            ``manual`` this call will replace it. A caller that wants
            "re-detect" to mean something while a manual pick is active
            should not offer the action then, rather than rely on this
            function to refuse it.
        ip_lookup: injection point for tests; defaults to the real
            :func:`~pilight.location.ipgeo.geolocate_by_ip`.
        cities: injection point for tests; defaults to the real bundled
            34k-row database.

    Raises:
        NoLocationAvailableError: no manual override, no cache (or
            ``force_redetect``), IP geolocation failed, and no ``picker``
            was supplied.
    """
    if manual is not None:
        result = _with_resolved_timezone(
            _from_city(manual, source="manual"),
            ip_timezone=None,
            city_timezone=manual.timezone,
        )
        save_cached_location(cache_path, result)
        return result

    if not force_redetect:
        cached = load_cached_location(cache_path)
        if cached is not None:
            result = _with_resolved_timezone(
                cached, ip_timezone=None, city_timezone=cached.timezone
            )
            if result != cached:
                save_cached_location(cache_path, result)
            return result

    try:
        ip_result = ip_lookup()
    except NoNetworkError:
        if picker is None:
            raise NoLocationAvailableError(
                "no cache, no manual override, IP geolocation failed, and no "
                "offline picker was supplied -- a city must be chosen"
            ) from None
        pool = cities if cities is not None else load_city_database()
        chosen = picker(pool)
        result = _with_resolved_timezone(
            _from_city(chosen, source="city_picker"),
            ip_timezone=None,
            city_timezone=chosen.timezone,
        )
    else:
        ip_location = ResolvedLocation(
            lat=ip_result.lat,
            lon=ip_result.lon,
            city=ip_result.city,
            country=ip_result.country,
            timezone=ip_result.timezone,
            source="ip",
        )
        result = _with_resolved_timezone(
            ip_location, ip_timezone=ip_result.timezone, city_timezone=None
        )

    save_cached_location(cache_path, result)
    return result
