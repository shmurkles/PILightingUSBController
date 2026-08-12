"""Tests for SchedulerDaemon: the stateful loop around compute_schedule()."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from pilight.config import ManualOverride, PiLightConfig, load_config, save_config
from pilight.location import ResolvedLocation
from pilight.power import PowerBackendError
from pilight.scheduler import SchedulerDaemon
from pilight.status import DaemonStatus, load_status, save_status

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


def test_status_file_written_after_a_successful_tick(tmp_path):
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    daemon.tick()
    status = load_status(daemon._status_path)
    assert status is not None
    assert status.actual_on is True
    assert status.desired_on is True
    assert status.updated_at == now


def test_status_records_a_transition(tmp_path):
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)  # desired True, default actual False
    daemon.tick()
    status = load_status(daemon._status_path)
    assert status.last_transition_at == now
    assert status.last_transition_to is True


def test_status_last_transition_is_unchanged_on_a_tick_with_no_switch(tmp_path):
    path = tmp_path / "config.json"
    save_config(path, _config(off_time="23:00"))
    t1 = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)
    t2 = datetime(2026, 6, 1, 21, 5, tzinfo=TZ)
    now_box = {"now": t1}
    daemon = SchedulerDaemon(path, now_fn=lambda: now_box["now"], get_sunset_fn=_fake_sunset(time(20, 0)))

    daemon.tick()  # switches on at t1
    now_box["now"] = t2
    daemon.tick()  # still desired on, no switch

    status = load_status(daemon._status_path)
    assert status.last_transition_at == t1
    assert status.updated_at == t2  # heartbeat still refreshes every tick


def test_status_seeds_last_transition_from_an_existing_file_on_restart(tmp_path):
    config_path = tmp_path / "config.json"
    # Backend's initial state matches what the prior status claims (True),
    # so this tick reconciles cleanly with no new switch -- otherwise a real
    # mismatch against the live backend would itself cause a legitimate new
    # transition, which is a different scenario from the one under test.
    save_config(
        config_path,
        _config(off_time="23:00", backend_settings={"dryrun": {"initial_state": True}}),
    )
    status_path = tmp_path / "status.json"
    earlier = datetime(2026, 6, 1, 20, 0, tzinfo=TZ)
    save_status(
        status_path,
        DaemonStatus(
            actual_on=True,
            desired_on=True,
            last_transition_at=earlier,
            last_transition_to=True,
            updated_at=earlier,
        ),
    )

    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)  # still within the window, no new switch needed
    daemon = SchedulerDaemon(
        config_path, status_path=status_path, now_fn=lambda: now, get_sunset_fn=_fake_sunset(time(20, 0))
    )
    daemon.tick()

    status = load_status(status_path)
    assert status.last_transition_at == earlier  # preserved, not reset to None
    assert status.updated_at == now  # heartbeat still moves forward


def test_override_forces_on_regardless_of_schedule(tmp_path):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)  # well outside the normal window
    until = datetime(2026, 1, 1, 18, 0, tzinfo=TZ)
    config = _config(off_time="23:00", manual_override=ManualOverride(state=True, until=until))
    daemon = _daemon(tmp_path, config, now=now)
    daemon.tick()
    assert daemon._backend.get_power() is True


def test_override_forces_off_regardless_of_schedule(tmp_path):
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)  # inside the normal on-window
    until = datetime(2026, 6, 1, 22, 0, tzinfo=TZ)
    config = _config(
        off_time="23:00",
        backend_settings={"dryrun": {"initial_state": True}},
        manual_override=ManualOverride(state=False, until=until),
    )
    daemon = _daemon(tmp_path, config, now=now)
    daemon.tick()
    assert daemon._backend.get_power() is False


def test_override_lapses_and_is_cleared_from_config(tmp_path):
    path = tmp_path / "config.json"
    until = datetime(2026, 6, 1, 20, 30, tzinfo=TZ)
    save_config(
        path, _config(off_time="23:00", manual_override=ManualOverride(state=False, until=until))
    )
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)  # past `until`
    daemon = SchedulerDaemon(path, now_fn=lambda: now, get_sunset_fn=_fake_sunset(time(20, 0)))
    daemon.tick()

    assert load_config(path).manual_override is None
    # Normal scheduling resumed: 21:00 is within the 20:00-23:00 window -> on.
    assert daemon._backend.get_power() is True


def test_override_still_active_is_not_cleared(tmp_path):
    path = tmp_path / "config.json"
    until = datetime(2026, 6, 1, 22, 0, tzinfo=TZ)
    save_config(
        path, _config(off_time="23:00", manual_override=ManualOverride(state=False, until=until))
    )
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)  # before `until`
    daemon = SchedulerDaemon(path, now_fn=lambda: now, get_sunset_fn=_fake_sunset(time(20, 0)))
    daemon.tick()

    assert load_config(path).manual_override is not None


def test_override_is_honored_fresh_after_a_daemon_restart(tmp_path):
    path = tmp_path / "config.json"
    until = datetime(2026, 1, 1, 18, 0, tzinfo=TZ)
    save_config(
        path, _config(off_time="23:00", manual_override=ManualOverride(state=True, until=until))
    )
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)  # before `until`, outside the normal window
    # A brand new SchedulerDaemon instance simulates a restart: no in-memory
    # state carried over, only what's on disk.
    daemon = SchedulerDaemon(path, now_fn=lambda: now, get_sunset_fn=_fake_sunset(time(20, 0)))
    daemon.tick()
    assert daemon._backend.get_power() is True


def test_location_and_sunset_logged_on_first_tick(tmp_path, caplog):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    with caplog.at_level(logging.INFO):
        daemon.tick()
    assert "Portland" in caplog.text
    assert "sunset=" in caplog.text


def test_location_not_relogged_on_a_tick_with_no_config_change(tmp_path, caplog):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    daemon.tick()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        daemon.tick()
    assert "Portland" not in caplog.text


def test_location_relogged_after_a_config_change(tmp_path, caplog):
    path = tmp_path / "config.json"
    now = datetime(2026, 6, 1, 12, 0, tzinfo=TZ)
    save_config(path, _config(off_time="23:00"))
    daemon = SchedulerDaemon(path, now_fn=lambda: now, get_sunset_fn=_fake_sunset(time(20, 0)))
    daemon.tick()
    caplog.clear()

    save_config(path, _config(off_time="22:00"))
    os.utime(path, (1_700_000_500, 1_700_000_500))
    with caplog.at_level(logging.INFO):
        daemon.tick()
    assert "Portland" in caplog.text


def test_transition_log_includes_sunset_on_off_and_reason(tmp_path, caplog):
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    with caplog.at_level(logging.INFO):
        daemon.tick()
    assert "sunset=" in caplog.text
    assert "on=" in caplog.text
    assert "off=" in caplog.text
    assert "reason=scheduled" in caplog.text


def test_transition_log_reason_is_manual_override_when_forced(tmp_path, caplog):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)
    until = datetime(2026, 1, 1, 18, 0, tzinfo=TZ)
    config = _config(off_time="23:00", manual_override=ManualOverride(state=True, until=until))
    daemon = _daemon(tmp_path, config, now=now)
    with caplog.at_level(logging.INFO):
        daemon.tick()
    assert "reason=manual override" in caplog.text


def test_no_change_tick_produces_no_info_logs(tmp_path, caplog):
    # Outside the window, default backend state already off -> no switch,
    # no reload, no transition. Story 12: routine ticks stay quiet.
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    daemon.tick()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        daemon.tick()
    assert caplog.text == ""


def test_backend_error_does_not_update_status(tmp_path, monkeypatch):
    class FlakyBackend:
        def describe(self):
            return "flaky"

        def get_power(self):
            return False

        def set_power(self, on):
            raise PowerBackendError("simulated failure")

    monkeypatch.setattr("pilight.scheduler.daemon.create_backend", lambda cfg: FlakyBackend())
    now = datetime(2026, 6, 1, 21, 0, tzinfo=TZ)
    daemon = _daemon(tmp_path, _config(off_time="23:00"), now=now)
    daemon.tick()
    assert load_status(daemon._status_path) is None
