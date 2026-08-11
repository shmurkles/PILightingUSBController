"""Tests for Story 3 -- sunset calculation."""

from __future__ import annotations

import socket
from datetime import date, datetime, timedelta

import pytest

from pilight.sun import PolarDayError, get_sunset

# Portland, OR -- the location used throughout EPIC.md's GUI mockup.
PORTLAND = {"lat": 45.5152, "lon": -122.6784, "tz": "America/Los_Angeles"}

# NOAA Solar Calculator (https://gml.noaa.gov/grad/solcalc/table.php),
# lat=45.5152 lon=-122.6784, year 2026. Both solstices, both equinoxes.
NOAA_REFERENCE = [
    (date(2026, 3, 20), "19:23"),  # March equinox
    (date(2026, 6, 21), "21:03"),  # June solstice
    (date(2026, 9, 23), "19:06"),  # September equinox
    (date(2026, 12, 21), "16:30"),  # December solstice
]


def test_returns_timezone_aware_datetime():
    sunset = get_sunset(date(2026, 6, 21), **PORTLAND)
    assert isinstance(sunset, datetime)
    assert sunset.tzinfo is not None
    assert sunset.date() == date(2026, 6, 21)


@pytest.mark.parametrize("day,expected_hhmm", NOAA_REFERENCE)
def test_matches_noaa_solar_calculator(day, expected_hhmm):
    sunset = get_sunset(day, **PORTLAND)
    expected_time = datetime.strptime(expected_hhmm, "%H:%M").time()
    expected = datetime.combine(day, expected_time, tzinfo=sunset.tzinfo)
    assert abs(sunset - expected) <= timedelta(minutes=2)


def test_dst_spring_forward_offsets_are_correct():
    # 2026 US spring-forward is March 8.
    before = get_sunset(date(2026, 3, 7), **PORTLAND)
    after = get_sunset(date(2026, 3, 9), **PORTLAND)
    assert before.utcoffset() == timedelta(hours=-8)  # PST
    assert after.utcoffset() == timedelta(hours=-7)  # PDT

    # The transition day itself must not error.
    on_transition = get_sunset(date(2026, 3, 8), **PORTLAND)
    assert on_transition.tzinfo is not None


def test_dst_fall_back_offsets_are_correct():
    # 2026 US fall-back is November 1.
    before = get_sunset(date(2026, 10, 31), **PORTLAND)
    after = get_sunset(date(2026, 11, 2), **PORTLAND)
    assert before.utcoffset() == timedelta(hours=-7)  # PDT
    assert after.utcoffset() == timedelta(hours=-8)  # PST

    on_transition = get_sunset(date(2026, 11, 1), **PORTLAND)
    assert on_transition.tzinfo is not None


def test_polar_day_raises_typed_error():
    # Longyearbyen, Svalbard: midnight sun in June -- the sun never sets.
    with pytest.raises(PolarDayError):
        get_sunset(date(2026, 6, 21), lat=78.2232, lon=15.6267, tz="Arctic/Longyearbyen")


def test_never_touches_the_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("get_sunset attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)

    get_sunset(date(2026, 3, 20), **PORTLAND)
