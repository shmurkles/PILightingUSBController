"""Tests for the config schema and its per-field sanitization."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pilight.config import ManualOverride, PiLightConfig
from pilight.location import ResolvedLocation

TZ = ZoneInfo("America/Los_Angeles")

LOCATION = ResolvedLocation(
    lat=45.5152,
    lon=-122.6784,
    city="Portland",
    country="US",
    timezone="America/Los_Angeles",
    source="manual",
)


def test_defaults_round_trip_through_dict():
    config = PiLightConfig.defaults()
    restored = PiLightConfig.from_dict(config.to_dict())
    assert restored == config


def test_to_dict_is_directly_usable_by_create_backend():
    from pilight.power import DryRunBackend, create_backend

    config = PiLightConfig(backend="dryrun", backend_settings={"dryrun": {"initial_state": True}})
    backend = create_backend(config.to_dict())
    assert isinstance(backend, DryRunBackend)
    assert backend.get_power() is True


def test_offset_within_range_is_kept():
    config = PiLightConfig.from_dict({"offset_minutes": -45})
    assert config.offset_minutes == -45


def test_offset_above_range_is_clamped_and_logged(caplog):
    with caplog.at_level(logging.WARNING):
        config = PiLightConfig.from_dict({"offset_minutes": 999})
    assert config.offset_minutes == 180
    assert "clamped" in caplog.text


def test_offset_below_range_is_clamped_and_logged(caplog):
    with caplog.at_level(logging.WARNING):
        config = PiLightConfig.from_dict({"offset_minutes": -999})
    assert config.offset_minutes == -180
    assert "clamped" in caplog.text


def test_non_numeric_offset_falls_back_to_default(caplog):
    with caplog.at_level(logging.WARNING):
        config = PiLightConfig.from_dict({"offset_minutes": "soon"})
    assert config.offset_minutes == 0
    assert "not a number" in caplog.text


def test_valid_off_time_is_kept():
    config = PiLightConfig.from_dict({"off_time": "07:15"})
    assert config.off_time == "07:15"


def test_malformed_off_time_falls_back_to_default(caplog):
    with caplog.at_level(logging.WARNING):
        config = PiLightConfig.from_dict({"off_time": "not a time"})
    assert config.off_time == "23:30"
    assert "off_time" in caplog.text


def test_out_of_range_off_time_falls_back_to_default():
    config = PiLightConfig.from_dict({"off_time": "24:00"})
    assert config.off_time == "23:30"


def test_valid_location_round_trips():
    config = PiLightConfig.from_dict({"location": LOCATION.to_dict()})
    assert config.location == LOCATION


def test_missing_location_is_none():
    assert PiLightConfig.from_dict({}).location is None


def test_malformed_location_is_discarded(caplog):
    with caplog.at_level(logging.WARNING):
        config = PiLightConfig.from_dict({"location": {"lat": "not a number"}})
    assert config.location is None
    assert "location" in caplog.text


def test_location_that_is_not_an_object_is_discarded():
    config = PiLightConfig.from_dict({"location": "Portland"})
    assert config.location is None


def test_manual_override_round_trips():
    override = ManualOverride(state=True, until=datetime(2026, 6, 1, 23, 30, tzinfo=TZ))
    config = PiLightConfig.from_dict({"manual_override": override.to_dict()})
    assert config.manual_override == override


def test_malformed_manual_override_is_discarded(caplog):
    with caplog.at_level(logging.WARNING):
        config = PiLightConfig.from_dict({"manual_override": {"state": "on"}})  # missing "until"
    assert config.manual_override is None
    assert "manual_override" in caplog.text


def test_manual_override_that_is_not_an_object_is_discarded():
    config = PiLightConfig.from_dict({"manual_override": "on"})
    assert config.manual_override is None


def test_backend_name_is_normalized():
    config = PiLightConfig.from_dict({"backend": "  UhubCtl  "})
    assert config.backend == "uhubctl"


def test_unusable_backend_name_falls_back_to_default(caplog):
    with caplog.at_level(logging.WARNING):
        config = PiLightConfig.from_dict({"backend": ""})
    assert config.backend == "uhubctl"


def test_backend_settings_are_collected_from_top_level_object_keys():
    config = PiLightConfig.from_dict(
        {"backend": "uhubctl", "uhubctl": {"location": "2"}, "dryrun": {"initial_state": True}}
    )
    assert config.backend_settings == {
        "uhubctl": {"location": "2"},
        "dryrun": {"initial_state": True},
    }


def test_non_object_extra_keys_are_ignored_not_treated_as_backend_settings():
    config = PiLightConfig.from_dict({"some_string_field": "value", "some_number": 5})
    assert config.backend_settings == {}


def test_schema_version_defaults_when_missing_or_wrong_type():
    assert PiLightConfig.from_dict({}).schema_version == 1
    assert PiLightConfig.from_dict({"schema_version": "one"}).schema_version == 1
