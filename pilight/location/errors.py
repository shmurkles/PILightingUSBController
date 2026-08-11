"""Error types for location resolution."""

from __future__ import annotations


class LocationError(Exception):
    """Base class for every failure this package can raise."""


class NoNetworkError(LocationError):
    """IP geolocation could not be reached (no network, timeout, or bad response).

    Not fatal to resolution as a whole -- the caller falls back to the offline
    city picker. Raised only by :mod:`pilight.location.ipgeo`; callers of the
    higher-level :func:`pilight.location.resolve_location` should not need to
    catch this directly.
    """


class NoLocationAvailableError(LocationError):
    """No location could be resolved by any mechanism.

    Raised by :func:`pilight.location.resolve_location` when there is no
    manual override, no cache, IP geolocation failed or was skipped, and no
    ``picker`` callable was supplied to ask the user. The caller must supply
    one of those before a schedule can be computed at all.
    """


class CityDatabaseError(LocationError):
    """The bundled city database could not be loaded or is empty."""


class TimezoneUnavailableError(LocationError):
    """No timezone could be determined from the system, IP lookup, or city record."""
