"""Tests for the bundled city database."""

from __future__ import annotations

import pytest

from pilight.location import CityDatabaseError, CityRecord, load_city_database, nearest_city
from pilight.location.citydb import haversine_km

FIXTURE = "\n".join(
    [
        "name\tcountry\tlat\tlon\ttimezone",
        "Portland\tUS\t45.5152\t-122.6784\tAmerica/Los_Angeles",
        "Seattle\tUS\t47.6062\t-122.3321\tAmerica/Los_Angeles",
        "Denver\tUS\t39.7392\t-104.9903\tAmerica/Denver",
    ]
)


def _write_fixture(tmp_path):
    path = tmp_path / "cities.tsv"
    path.write_text(FIXTURE, encoding="utf-8")
    return path


def test_loads_rows_from_a_given_path(tmp_path):
    cities = load_city_database(_write_fixture(tmp_path))
    assert len(cities) == 3
    assert cities[0] == CityRecord("Portland", "US", 45.5152, -122.6784, "America/Los_Angeles")


def test_missing_file_raises_typed_error(tmp_path):
    with pytest.raises(CityDatabaseError):
        load_city_database(tmp_path / "does-not-exist.tsv")


def test_empty_file_raises_typed_error(tmp_path):
    path = tmp_path / "empty.tsv"
    path.write_text("name\tcountry\tlat\tlon\ttimezone\n", encoding="utf-8")
    with pytest.raises(CityDatabaseError):
        load_city_database(path)


def test_haversine_is_zero_for_the_same_point():
    assert haversine_km(45.5, -122.6, 45.5, -122.6) == pytest.approx(0.0, abs=1e-9)


def test_haversine_matches_known_portland_to_seattle_distance():
    # Real-world great-circle distance is ~233 km.
    km = haversine_km(45.5152, -122.6784, 47.6062, -122.3321)
    assert km == pytest.approx(233, abs=5)


def test_nearest_city_picks_the_closest_one(tmp_path):
    cities = load_city_database(_write_fixture(tmp_path))
    nearest = nearest_city(45.6, -122.7, cities)
    assert nearest.name == "Portland"


def test_nearest_city_against_the_real_bundled_database():
    nearest = nearest_city(45.5152, -122.6784)
    assert nearest.name == "Portland"
    assert nearest.country == "US"


def test_nearest_city_empty_pool_raises():
    with pytest.raises(CityDatabaseError):
        nearest_city(0, 0, [])
