"""Smoke tests for the Tkinter GUI.

Need a real display -- skipped when $DISPLAY isn't set (a plain headless
SSH session, most CI). now_fn/get_sunset_fn are injected with fixed values
throughout so these tests don't depend on the real date or the real Pi's
location -- an "invalid window" test built on real sunset times would be
flaky depending on the season it happens to run in.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from pilight.config import PiLightConfig, load_config, save_config
from pilight.gui.app import PiLightGUI
from pilight.location import ResolvedLocation

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"), reason="no DISPLAY available for Tkinter"
)

TZ = ZoneInfo("America/Edmonton")
LOCATION = ResolvedLocation(53.5501, -113.4687, "Edmonton", "CA", "America/Edmonton", "ip")
FIXED_NOW = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)


def _fixed_sunset(sunset_time: time = time(20, 0)):
    def _get(d: date, *, lat, lon, tz):
        return datetime.combine(d, sunset_time, tzinfo=TZ)

    return _get


def _make_app(tmp_path, *, sunset_time=time(20, 0), now=FIXED_NOW, **overrides):
    fields = {"offset_minutes": 0, "off_time": "23:00", "location": LOCATION}
    fields.update(overrides)
    config = PiLightConfig(**fields)
    path = tmp_path / "config.json"
    save_config(path, config)
    return PiLightGUI(
        path, now_fn=lambda: now, get_sunset_fn=_fixed_sunset(sunset_time)
    )


def test_construction_survives_a_real_event_loop_pump(tmp_path):
    """ttk.Scale's command callback fires on a deferred Tcl event, not
    synchronously inside .set() -- a bug in it is invisible to
    update_idletasks() (used by other tests here) and silent by default,
    since Tkinter prints and swallows exceptions raised from callbacks
    rather than propagating them. Re-raise here so a regression actually
    fails the test instead of only showing up as a black window over Pi
    Connect."""
    app = _make_app(tmp_path)
    errors = []
    app.root.report_callback_exception = lambda *exc_info: errors.append(exc_info)
    try:
        app.root.update()
    finally:
        app.destroy()
    assert errors == []


def test_window_constructs_with_fixed_non_resizable_size(tmp_path):
    app = _make_app(tmp_path)
    try:
        assert app.root.resizable() == (0, 0)
        app.root.update_idletasks()
        assert app.root.winfo_reqwidth() > 0
    finally:
        app.destroy()


def test_dark_theme_colors_are_set_explicitly(tmp_path):
    app = _make_app(tmp_path)
    try:
        assert app.root.cget("background") == "#1e1e1e"
    finally:
        app.destroy()


def test_dragging_the_slider_snaps_and_saves(tmp_path):
    app = _make_app(tmp_path)
    try:
        app._on_offset_change("37")  # not a multiple of 15
        assert app.config.offset_minutes == 30
        assert load_config(app.config_path).offset_minutes == 30
    finally:
        app.destroy()


def test_slider_readout_shows_offset_and_on_time(tmp_path):
    app = _make_app(tmp_path)
    try:
        app._on_offset_change("60")  # sunset 20:00 + 60 min -> on at 21:00
        assert "+1:00" in app.on_time_label.cget("text")
        assert "21:00" in app.on_time_label.cget("text")
    finally:
        app.destroy()


def test_changing_off_time_saves(tmp_path):
    app = _make_app(tmp_path)
    try:
        app.off_time_var.set("07:15")
        app._on_off_time_change()
        assert app.config.off_time == "07:15"
        assert load_config(app.config_path).off_time == "07:15"
    finally:
        app.destroy()


def test_settings_persist_across_a_fresh_window(tmp_path):
    app1 = _make_app(tmp_path, offset_minutes=-30)
    path = app1.config_path
    app1.destroy()

    app2 = PiLightGUI(path, now_fn=lambda: FIXED_NOW, get_sunset_fn=_fixed_sunset())
    try:
        assert app2.config.offset_minutes == -30
    finally:
        app2.destroy()


def test_warning_shown_for_an_invalid_window(tmp_path):
    # sunset 21:30 + 180 min offset -> on_time past midnight; off_time 22:00
    # combined with the rolled-forward date balloons the window past 20h.
    app = _make_app(tmp_path, sunset_time=time(21, 30), offset_minutes=180, off_time="22:00")
    try:
        assert "never turns the light on" in app.warning_label.cget("text")
    finally:
        app.destroy()


def test_no_warning_for_a_normal_window(tmp_path):
    app = _make_app(tmp_path, offset_minutes=0, off_time="23:00")
    try:
        assert app.warning_label.cget("text") == ""
    finally:
        app.destroy()


def test_status_dot_reflects_the_scheduled_state(tmp_path):
    # FIXED_NOW is 21:00; window 20:00-23:00 -> currently on.
    app = _make_app(tmp_path, offset_minutes=0, off_time="23:00")
    try:
        assert app.status_text.cget("text") == "on"
    finally:
        app.destroy()

    # FIXED_NOW is 21:00; window already closed at 20:30 -> currently off.
    app2 = _make_app(tmp_path, offset_minutes=0, off_time="20:30")
    try:
        assert app2.status_text.cget("text") == "off"
    finally:
        app2.destroy()


def test_missing_location_does_not_crash_and_shows_a_hint(tmp_path):
    app = _make_app(tmp_path, location=None)
    try:
        assert "not yet resolved" in app.corner_label.cget("text")
        assert app.status_text.cget("text") == "unknown"
    finally:
        app.destroy()


def test_corner_label_shows_city_and_sunset(tmp_path):
    app = _make_app(tmp_path)
    try:
        text = app.corner_label.cget("text")
        assert "Edmonton" in text
        assert "20:00" in text
    finally:
        app.destroy()
