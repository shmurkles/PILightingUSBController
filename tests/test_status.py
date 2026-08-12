"""Tests for the daemon status file."""

from __future__ import annotations

import stat
from datetime import datetime
from zoneinfo import ZoneInfo

from pilight.status import DaemonStatus, load_status, save_status

TZ = ZoneInfo("America/Edmonton")


def _status(**overrides) -> DaemonStatus:
    fields = dict(
        actual_on=True,
        desired_on=True,
        last_transition_at=datetime(2026, 8, 10, 21, 9, tzinfo=TZ),
        last_transition_to=True,
        updated_at=datetime(2026, 8, 10, 21, 30, tzinfo=TZ),
    )
    fields.update(overrides)
    return DaemonStatus(**fields)


def test_missing_status_returns_none(tmp_path):
    assert load_status(tmp_path / "status.json") is None


def test_round_trips_through_disk(tmp_path):
    path = tmp_path / "status.json"
    status = _status()
    save_status(path, status)
    assert load_status(path) == status


def test_corrupt_status_returns_none_not_an_exception(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("not json", encoding="utf-8")
    assert load_status(path) is None


def test_none_actual_on_round_trips_as_unknown(tmp_path):
    path = tmp_path / "status.json"
    save_status(path, _status(actual_on=None))
    assert load_status(path).actual_on is None


def test_no_transition_yet_round_trips_as_none(tmp_path):
    path = tmp_path / "status.json"
    save_status(path, _status(last_transition_at=None, last_transition_to=None))
    loaded = load_status(path)
    assert loaded.last_transition_at is None
    assert loaded.last_transition_to is None


def test_is_stale_false_when_recent():
    status = _status(updated_at=datetime(2026, 8, 10, 21, 30, tzinfo=TZ))
    now = datetime(2026, 8, 10, 21, 30, 30, tzinfo=TZ)  # 30s later
    assert status.is_stale(now=now) is False


def test_is_stale_true_when_old():
    status = _status(updated_at=datetime(2026, 8, 10, 21, 30, tzinfo=TZ))
    now = datetime(2026, 8, 10, 21, 32, 0, tzinfo=TZ)  # 120s later
    assert status.is_stale(now=now) is True


def test_write_is_atomic_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "status.json"
    save_status(path, _status())
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_written_file_is_group_writable(tmp_path):
    path = tmp_path / "status.json"
    save_status(path, _status())
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & stat.S_IWGRP
