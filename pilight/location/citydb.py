"""The bundled city database: nearest-city lookup with no network access.

Not how sunset gets calculated (that's pure lat/lon math -- see pilight.sun).
This exists to give the user a human-readable "near <city>" label and an
offline picker when there's no network at first run. See RESEARCH.md §4.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

from .errors import CityDatabaseError

_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class CityRecord:
    """One row of the bundled GeoNames extract."""

    name: str
    country: str
    lat: float
    lon: float
    timezone: str


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@lru_cache(maxsize=4)
def load_city_database(path: Path | None = None) -> tuple[CityRecord, ...]:
    """Load the bundled (or a given) city database.

    Cached per distinct ``path`` (the bundled database is parsed at most
    once per process): 34k rows of the same file is one read too many.

    Args:
        path: override the bundled ``pilight/data/cities15000.tsv``. Mainly
            for tests, which pass a small fixture file instead of parsing
            34,000 real rows.

    Raises:
        CityDatabaseError: the file is missing, unreadable, or empty.
    """
    try:
        if path is not None:
            text = path.read_text(encoding="utf-8")
        else:
            text = resources.files("pilight.data").joinpath("cities15000.tsv").read_text(
                encoding="utf-8"
            )
    except OSError as exc:
        raise CityDatabaseError(f"could not read city database: {exc}") from exc

    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    records = [
        CityRecord(
            name=row["name"],
            country=row["country"],
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            timezone=row["timezone"],
        )
        for row in reader
        if row["timezone"]
    ]
    if not records:
        raise CityDatabaseError("city database loaded but contained no usable rows")
    return tuple(records)


def nearest_city(
    lat: float, lon: float, cities: list[CityRecord] | tuple[CityRecord, ...] | None = None
) -> CityRecord:
    """The closest city to (lat, lon) by great-circle distance.

    Args:
        cities: search this list instead of the bundled database (tests use
            a small fixture; production code omits this and gets the real
            34k-row database, cached after the first call in a process).

    A linear scan over ~34k rows in plain Python takes a few tens of
    milliseconds -- see RESEARCH.md §4 for why that's fine and no index is
    needed.
    """
    pool = cities if cities is not None else load_city_database()
    if not pool:
        raise CityDatabaseError("no cities to search")
    return min(pool, key=lambda c: haversine_km(lat, lon, c.lat, c.lon))
