"""Tests for the `python -m pilight.location resolve` CLI wiring."""

from __future__ import annotations

import pytest

import pilight.location.__main__ as cli
from pilight.config import PiLightConfig
from pilight.location import CityRecord, ResolvedLocation

LOCATION = ResolvedLocation(45.5152, -122.6784, "Portland", "US", "America/Los_Angeles", "ip")


def test_resolve_writes_the_location_into_the_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"

    captured = {}

    def fake_resolve_location(cache_path, *, picker, force_redetect):
        captured["cache_path"] = cache_path
        captured["force_redetect"] = force_redetect
        return LOCATION

    monkeypatch.setattr(cli, "resolve_location", fake_resolve_location)

    cli.main(["resolve", str(config_path)])

    from pilight.config import load_config

    saved = load_config(config_path)
    assert saved.location == LOCATION
    assert captured["cache_path"] == config_path.with_name("location_cache.json")
    assert captured["force_redetect"] is False


def test_redetect_flag_is_passed_through(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    captured = {}

    def fake_resolve_location(cache_path, *, picker, force_redetect):
        captured["force_redetect"] = force_redetect
        return LOCATION

    monkeypatch.setattr(cli, "resolve_location", fake_resolve_location)
    cli.main(["resolve", str(config_path), "--redetect"])
    assert captured["force_redetect"] is True


def test_resolve_preserves_other_existing_config_fields(tmp_path, monkeypatch):
    from pilight.config import save_config

    config_path = tmp_path / "config.json"
    save_config(config_path, PiLightConfig(offset_minutes=-45, off_time="22:15"))

    monkeypatch.setattr(cli, "resolve_location", lambda cache_path, *, picker, force_redetect: LOCATION)
    cli.main(["resolve", str(config_path)])

    from pilight.config import load_config

    saved = load_config(config_path)
    assert saved.offset_minutes == -45
    assert saved.off_time == "22:15"
    assert saved.location == LOCATION


def test_prompt_picker_filters_and_selects_by_index(monkeypatch):
    cities = [
        CityRecord("Portland", "US", 45.5, -122.6, "America/Los_Angeles"),
        CityRecord("Portland", "GB", 50.7, -2.4, "Europe/London"),
        CityRecord("Seattle", "US", 47.6, -122.3, "America/Los_Angeles"),
    ]
    inputs = iter(["portland", "1"])
    monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))
    chosen = cli._prompt_picker(cities)
    assert chosen.country == "GB"


def test_prompt_picker_raises_when_nothing_matches(monkeypatch):
    cities = [CityRecord("Portland", "US", 45.5, -122.6, "America/Los_Angeles")]
    monkeypatch.setattr("builtins.input", lambda *_a: "nowhere-at-all")
    with pytest.raises(SystemExit):
        cli._prompt_picker(cities)
