"""Tests for config file load/save: missing file, corruption, atomic writes."""

from __future__ import annotations

import json
import logging

from pilight.config import PiLightConfig, load_config, save_config


def test_missing_file_gets_defaults_written_to_disk(tmp_path):
    path = tmp_path / "config.json"
    config = load_config(path)
    assert config == PiLightConfig.defaults()
    assert path.exists()
    assert PiLightConfig.from_dict(json.loads(path.read_text())) == config


def test_existing_valid_file_loads_correctly(tmp_path):
    path = tmp_path / "config.json"
    save_config(path, PiLightConfig(offset_minutes=-30, off_time="22:00"))
    loaded = load_config(path)
    assert loaded.offset_minutes == -30
    assert loaded.off_time == "22:00"


def test_corrupt_json_falls_back_to_defaults_without_touching_the_file(tmp_path, caplog):
    path = tmp_path / "config.json"
    path.write_text("{not valid json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        config = load_config(path)
    assert config == PiLightConfig.defaults()
    assert path.read_text(encoding="utf-8") == "{not valid json"
    assert "corrupt" in caplog.text


def test_json_that_is_not_an_object_falls_back_to_defaults(tmp_path, caplog):
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        config = load_config(path)
    assert config == PiLightConfig.defaults()
    assert path.read_text(encoding="utf-8") == "[1, 2, 3]"


def test_unreadable_file_falls_back_to_defaults(tmp_path, caplog):
    path = tmp_path / "missing-after-check.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o000)
    try:
        with caplog.at_level(logging.ERROR):
            config = load_config(path)
        assert config == PiLightConfig.defaults()
    finally:
        path.chmod(0o644)


def test_save_is_atomic_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "config.json"
    save_config(path, PiLightConfig.defaults())
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "config.json"
    save_config(path, PiLightConfig.defaults())
    assert path.exists()
