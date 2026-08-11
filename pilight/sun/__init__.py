"""Sunset calculation.

    from datetime import date
    from pilight.sun import get_sunset

    sunset = get_sunset(date.today(), lat=45.5152, lon=-122.6784, tz="America/Los_Angeles")

Pure arithmetic (the NOAA solar equations, via astral) -- no network call, ever.
See RESEARCH.md §3 for why this beats a precomputed table or a weather API.
"""

from .sunset import PolarDayError, SunError, get_sunset

__all__ = ["PolarDayError", "SunError", "get_sunset"]
