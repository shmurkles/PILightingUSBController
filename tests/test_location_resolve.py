"""Tests for resolve_location()'s priority order: manual -> cache -> IP -> picker."""

from __future__ import annotations

import pytest

from pilight.location import CityRecord, NoLocationAvailableError
from pilight.location.errors import NoNetworkError
from pilight.location.ipgeo import IPLocation
from pilight.location.resolve import resolve_location

PORTLAND = CityRecord("Portland", "US", 45.5152, -122.6784, "America/Los_Angeles")
SEATTLE = CityRecord("Seattle", "US", 47.6062, -122.3321, "America/Los_Angeles")
IP_RESULT = IPLocation(45.5, -122.6, "Portland", "United States", "America/Los_Angeles")


def _boom():
    raise AssertionError("ip_lookup should not have been called")


def _no_network():
    raise NoNetworkError("offline")


@pytest.fixture(autouse=True)
def _no_real_system_timezone(monkeypatch):
    """Each test controls its own timezone story; the real device's system
    timezone would otherwise win every time and hide the ip/city fallback
    plumbing this module is responsible for."""
    monkeypatch.setattr("pilight.location.timezone.read_system_timezone", lambda: None)


def test_manual_override_wins_and_persists_across_calls(tmp_path):
    cache_path = tmp_path / "location.json"
    result = resolve_location(cache_path, manual=PORTLAND, ip_lookup=lambda: IP_RESULT)
    assert result.source == "manual"
    assert result.city == "Portland"

    again = resolve_location(cache_path, ip_lookup=_boom)
    assert again.source == "manual"
    assert again.city == "Portland"


def test_cache_hit_skips_ip_lookup(tmp_path):
    cache_path = tmp_path / "location.json"
    resolve_location(cache_path, manual=PORTLAND)
    resolve_location(cache_path, ip_lookup=_boom)  # would raise if called


def test_falls_back_to_ip_geolocation_when_no_cache(tmp_path):
    cache_path = tmp_path / "location.json"
    result = resolve_location(cache_path, ip_lookup=lambda: IP_RESULT)
    assert result.source == "ip"
    assert result.city == "Portland"
    assert result.timezone == "America/Los_Angeles"
    assert cache_path.exists()


def test_ip_result_is_cached_for_next_time(tmp_path):
    cache_path = tmp_path / "location.json"
    resolve_location(cache_path, ip_lookup=lambda: IP_RESULT)
    resolve_location(cache_path, ip_lookup=_boom)  # would raise if called


def test_falls_back_to_offline_picker_when_ip_fails(tmp_path):
    cache_path = tmp_path / "location.json"
    result = resolve_location(
        cache_path,
        ip_lookup=_no_network,
        picker=lambda cities: SEATTLE,
        cities=[PORTLAND, SEATTLE],
    )
    assert result.source == "city_picker"
    assert result.city == "Seattle"
    assert cache_path.exists()


def test_raises_when_ip_fails_and_no_picker_given(tmp_path):
    cache_path = tmp_path / "location.json"
    with pytest.raises(NoLocationAvailableError):
        resolve_location(cache_path, ip_lookup=_no_network)


def test_force_redetect_bypasses_the_cache(tmp_path):
    cache_path = tmp_path / "location.json"
    resolve_location(cache_path, manual=PORTLAND)
    result = resolve_location(cache_path, force_redetect=True, ip_lookup=lambda: IP_RESULT)
    assert result.source == "ip"


def test_system_timezone_overrides_ip_timezone(tmp_path, monkeypatch):
    monkeypatch.setattr("pilight.location.timezone.read_system_timezone", lambda: "Fake/System")
    cache_path = tmp_path / "location.json"
    result = resolve_location(cache_path, ip_lookup=lambda: IP_RESULT)
    assert result.timezone == "Fake/System"


def test_cache_hit_still_prefers_a_now_available_system_timezone(tmp_path, monkeypatch):
    cache_path = tmp_path / "location.json"
    resolve_location(cache_path, ip_lookup=lambda: IP_RESULT)  # cached tz: America/Los_Angeles

    monkeypatch.setattr("pilight.location.timezone.read_system_timezone", lambda: "Fake/System")
    result = resolve_location(cache_path, ip_lookup=_boom)
    assert result.timezone == "Fake/System"
