"""Tests for the GUI's pure formatting/snapping helpers -- no display needed."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pilight.gui.formatting import format_clock, format_offset, off_time_choices, snap_to_step

TZ = ZoneInfo("America/Los_Angeles")


def test_snap_rounds_to_nearest_quarter_hour():
    assert snap_to_step(7) == 0
    assert snap_to_step(8) == 15
    assert snap_to_step(-8) == -15
    assert snap_to_step(22) == 15
    assert snap_to_step(23) == 30


def test_snap_is_idempotent_on_already_snapped_values():
    for m in range(-180, 181, 15):
        assert snap_to_step(m) == m


def test_format_offset_negative():
    assert format_offset(-45) == "-0:45"


def test_format_offset_positive():
    assert format_offset(90) == "+1:30"


def test_format_offset_zero():
    assert format_offset(0) == "0:00"


def test_format_clock():
    assert format_clock(datetime(2026, 6, 1, 19, 38, tzinfo=TZ)) == "19:38"


def test_off_time_choices_covers_the_whole_day_in_order():
    choices = off_time_choices()
    assert choices[0] == "00:00"
    assert choices[-1] == "23:45"
    assert len(choices) == 96
    assert choices == sorted(choices)


def test_off_time_choices_are_all_quarter_hours():
    for value in off_time_choices():
        _hh, mm = value.split(":")
        assert int(mm) in (0, 15, 30, 45)
