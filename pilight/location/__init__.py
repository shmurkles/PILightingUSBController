"""Location resolution -- Story 4.

    from pilight.location import resolve_location

    result = resolve_location(cache_path=CACHE_PATH)
    print(result.lat, result.lon, result.timezone, result.source)

Resolution order: manual override -> cached value -> IP geolocation (once) ->
offline city picker. See RESEARCH.md §2 for why this order and why IP lookup
is accurate enough. The city database (Story 4's other half) is used both as
the offline picker's source list and, via `nearest_city`, to produce a
human-readable "near <city>" label for any lat/lon.
"""

from .cache import load_cached_location, save_cached_location
from .citydb import CityRecord, load_city_database, nearest_city
from .errors import (
    CityDatabaseError,
    LocationError,
    NoLocationAvailableError,
    NoNetworkError,
    TimezoneUnavailableError,
)
from .model import LocationSource, ResolvedLocation
from .resolve import resolve_location
from .timezone import resolve_timezone

__all__ = [
    "CityDatabaseError",
    "CityRecord",
    "LocationError",
    "LocationSource",
    "NoLocationAvailableError",
    "NoNetworkError",
    "ResolvedLocation",
    "TimezoneUnavailableError",
    "load_cached_location",
    "load_city_database",
    "nearest_city",
    "resolve_location",
    "resolve_timezone",
    "save_cached_location",
]
