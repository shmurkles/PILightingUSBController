"""Tests for SchedulerDaemon: the stateful loop around compute_schedule()."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from pilight.config import PiLightConfig, save_config
from pilight.location import ResolvedLocation
from pilight.power import PowerBackendError
from pilight.scheduler import SchedulerDaemon

TZ = ZoneInfo("America/Los_Angeles")
LOCATION = ResolvedLocation(45.5152, -122.6784, "Portland", "US", "America/Los_Angeles", "manual")


def _config(**overrides) -> PiLightConfig:
    base = dict(
        offset_minutes=0,
        off_time="23:00",
        location=LOCATION,
        backend="dryrun",
        backend_settings={"dryrun": {"initial_state": False}},
    )
    base.update(overrides)
    return PiLightConfig(**base)


def _fake_sunset(sunset_time: time):
    def _get(d: date, *, lat, lon, tz):
        return datetime.combine(d, sunset_time, tzinfo=TZ)

    return _get


def _daemon(tmp_path, config, *, now, sunset_time=time(20, 0)):
    path = tmp_path / "config.json"
    save_config(path, config)
    return SchedulerDaemon(path, now_fn=lambda: now, get_sunset_fn=_fake_sunset(sunset_time))


def test_reboot_mid_window_switches_on_immediately(tmp_path):
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    daemon.tick()
    assert daemon._backend.get_power() is True
    assert daemon._backend.calls == [True]


def test_no_mismatch_means_no_switch_call(tmp_path):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)  # well outside the window; default state is off
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    daemon.tick()
    assert daemon._backend.calls == []


def test_unknown_initial_state_always_switches_once(tmp_path):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)  # desired off, but actual state is unknown
    config = _config(off_time="23:00", backend_settings={"dryrun": {"initial_state": None}})
    daemon = _daemon(tmp_path, config, now=now)
    daemon.tick()
    assert daemon._backend.calls == [False]


def test_config_changes_are_picked_up_without_restart(tmp_path):
    path = tmp_path / "config.json"
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)

    save_config(path, _config(off_time="20:30"))  # window 20:00-20:30, already closed by 21:00
    os.utime(path, (1_700_000_000, 1_700_000_000))
    daemon = SchedulerDaemon(path, now_fn=lambda: now, get_sunset_fn=_fake_sunset(time(20, 0)))
    daemon.tick()
    assert daemon._backend.get_power() is False

    save_config(path, _config(off_time="23:00"))  # now the window covers 21:00
    os.utime(path, (1_700_000_100, 1_700_000_100))
    daemon.tick()
    assert daemon._backend.get_power() is True


def test_backend_error_is_logged_and_daemon_keeps_running(tmp_path, monkeypatch, caplog):
    class FlakyBackend:
        def __init__(self):
            self.calls = []

        def describe(self):
            return "flaky test backend"

        def get_power(self):
            return False

        def set_power(self, on):
            self.calls.append(on)
            raise PowerBackendError("simulated failure")

    flaky = FlakyBackend()
    monkeypatch.setattr("pilight.scheduler.daemon.create_backend", lambda cfg: flaky)

    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)  # inside window -> desired True, mismatched
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)

    with caplog.at_level(logging.ERROR):
        daemon.tick()
    assert flaky.calls == [True]
    assert "power backend error" in caplog.text

    with caplog.at_level(logging.ERROR):
        daemon.tick()  # retried, still doesn't raise
    assert flaky.calls == [True, True]


def test_missing_location_skips_the_tick_without_raising(tmp_path, caplog):
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(location=None), now=now)
    with caplog.at_level(logging.WARNING):
        daemon.tick()
    assert "no location resolved" in caplog.text
    assert daemon._backend is None


def test_invalid_window_logs_a_warning_and_leaves_the_light_off(tmp_path, caplog):
    now = datetime(2026, 6, 21, 10, 0, tzinfo=TZ)
    config = _config(offset_minutes=180, off_time="22:00")
    daemon = _daemon(tmp_path, config, now=now, sunset_time=time(21, 30))
    with caplog.at_level(logging.WARNING):
        daemon.tick()
    assert "invalid schedule window" in caplog.text
    assert daemon._backend.get_power() is False


def test_run_ticks_the_given_number_of_times_and_sleeps_between(tmp_path):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    sleeps: list[float] = []
    daemon.run(sleep_fn=sleeps.append, iterations=3)
    assert sleeps == [30.0, 30.0]
