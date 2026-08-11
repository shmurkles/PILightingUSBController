"""The resolved-location value type, shared by cache.py and resolve.py.

Split out to avoid a cache <-> resolve circular import: resolve_location()
needs the cache functions, and the cache functions need this type.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

LocationSource = Literal["manual", "ip", "city_picker"]


@dataclass(frozen=True)
class ResolvedLocation:
    """A location good enough to compute sunset with, plus where it came from.

    ``source`` records how this was *originally* determined -- manual pick,
    IP lookup, or the offline city picker -- so the UI can show it (Story 8's
    status corner). Loading a cached value preserves the original source
    rather than relabelling it: "manual" stays "manual" across restarts,
    which is what lets a manual pick keep overriding automatic detection
    forever, not just for one run.
    """

    lat: float
    lon: float
    city: str
    country: str
    timezone: str
    source: LocationSource

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ResolvedLocation:
        return cls(
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            city=str(data["city"]),
            country=str(data["country"]),
            timezone=str(data["timezone"]),
            source=data["source"],
        )
