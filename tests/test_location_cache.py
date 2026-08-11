"""Tests for the location disk cache."""

from __future__ import annotations

from dataclasses import replace

from pilight.location import ResolvedLocation
from pilight.location.cache import load_cached_location, save_cached_location

LOCATION = ResolvedLocation(
    lat=45.5152,
    lon=-122.6784,
    city="Portland",
    country="US",
    timezone="America/Los_Angeles",
    source="manual",
)


def test_missing_cache_returns_none(tmp_path):
    assert load_cached_location(tmp_path / "location.json") is None


def test_round_trips_through_disk(tmp_path):
    path = tmp_path / "nested" / "location.json"
    save_cached_location(path, LOCATION)
    assert load_cached_location(path) == LOCATION


def test_corrupt_cache_returns_none_not_an_exception(tmp_path):
    path = tmp_path / "location.json"
    path.write_text("not json", encoding="utf-8")
    assert load_cached_location(path) is None


def test_write_is_atomic_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "location.json"
    save_cached_location(path, LOCATION)
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_source_survives_the_round_trip(tmp_path):
    path = tmp_path / "location.json"
    save_cached_location(path, replace(LOCATION, source="ip"))
    assert load_cached_location(path).source == "ip"
