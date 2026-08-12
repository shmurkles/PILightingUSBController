"""Tests for compute_schedule(): the pure scheduling decision.

Every test here is a frozen-clock, no-I/O call -- Story 6's own acceptance
criterion for how this piece must be testable.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from pilight.scheduler.window import compute_schedule, next_transition_after
from pilight.sun import PolarDayError

TZ = ZoneInfo("America/Los_Angeles")


def _dt(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def _fixed_sunset(sunset_time: time):
    def _get(d: date) -> datetime:
        return datetime.combine(d, sunset_time, tzinfo=TZ)

    return _get


def test_same_day_window_before_on_time_is_off():
    decision = compute_schedule(_dt(2026, 6, 1, 19, 0), _fixed_sunset(time(20, 0)), 0, time(23, 0))
    assert decision.desired_on is False
    assert decision.window_valid


def test_same_day_window_inside_is_on():
    decision = compute_schedule(_dt(2026, 6, 1, 21, 0), _fixed_sunset(time(20, 0)), 0, time(23, 0))
    assert decision.desired_on is True


def test_same_day_window_after_off_time_is_off():
    decision = compute_schedule(_dt(2026, 6, 1, 23, 30), _fixed_sunset(time(20, 0)), 0, time(23, 0))
    assert decision.desired_on is False


def test_offset_shifts_on_time():
    # -60 min offset -> on_time 19:00; 19:30 should already be on.
    decision = compute_schedule(_dt(2026, 6, 1, 19, 30), _fixed_sunset(time(20, 0)), -60, time(23, 0))
    assert decision.desired_on is True


def test_midnight_crossing_window_is_on_before_midnight():
    decision = compute_schedule(_dt(2026, 6, 1, 23, 0), _fixed_sunset(time(20, 0)), 0, time(1, 0))
    assert decision.desired_on is True
    assert decision.off_time == _dt(2026, 6, 2, 1, 0)


def test_midnight_crossing_window_is_on_after_midnight():
    # 'today' is June 2nd; the active window started June 1st 20:00 and runs
    # to June 2nd 01:00 -- the "yesterday" candidate window.
    decision = compute_schedule(_dt(2026, 6, 2, 0, 30), _fixed_sunset(time(20, 0)), 0, time(1, 0))
    assert decision.desired_on is True


def test_midnight_crossing_window_is_off_after_it_closes():
    decision = compute_schedule(_dt(2026, 6, 2, 2, 0), _fixed_sunset(time(20, 0)), 0, time(1, 0))
    assert decision.desired_on is False


def test_midnight_crossing_window_is_off_well_before_it_opens():
    decision = compute_schedule(_dt(2026, 6, 2, 12, 0), _fixed_sunset(time(20, 0)), 0, time(1, 0))
    assert decision.desired_on is False


def test_reboot_mid_window_is_immediately_on():
    # No prior calls, no history -- a cold-start evaluation mid-window must
    # come back on immediately (the reboot-at-23:00 case).
    decision = compute_schedule(_dt(2026, 1, 15, 23, 0), _fixed_sunset(time(20, 0)), 0, time(23, 30))
    assert decision.desired_on is True


def test_extreme_offset_pushing_on_time_past_off_time_is_invalid():
    # sunset 21:30, offset +180 -> on_time 00:30 (tomorrow); off_time 22:00
    # combined with on_time's (tomorrow's) date is *after* on_time, so no
    # rollover happens and the window balloons to ~21.5 hours.
    decision = compute_schedule(_dt(2026, 6, 21, 10, 0), _fixed_sunset(time(21, 30)), 180, time(22, 0))
    assert decision.window_valid is False
    assert decision.desired_on is False
    assert decision.reason is not None


def test_zero_length_window_is_invalid():
    decision = compute_schedule(_dt(2026, 6, 1, 12, 0), _fixed_sunset(time(20, 0)), 0, time(20, 0))
    assert decision.window_valid is False
    assert decision.desired_on is False


def test_invalid_window_does_not_thrash_across_repeated_calls():
    sunset_for = _fixed_sunset(time(21, 30))
    decisions = [
        compute_schedule(_dt(2026, 6, 21, h, 0), sunset_for, 180, time(22, 0)) for h in range(0, 24, 2)
    ]
    assert all(d.desired_on is False for d in decisions)


def test_dst_spring_forward_window_stays_correct_across_the_transition():
    # 2026 US spring-forward is March 8. A window from 20:00 to 01:00 that
    # straddles the night of the transition should open/close at the right
    # *local* times regardless.
    sunset_for = _fixed_sunset(time(20, 0))
    before = compute_schedule(_dt(2026, 3, 8, 20, 30), sunset_for, 0, time(1, 0))
    after_midnight = compute_schedule(_dt(2026, 3, 9, 0, 30), sunset_for, 0, time(1, 0))
    closed = compute_schedule(_dt(2026, 3, 9, 1, 30), sunset_for, 0, time(1, 0))
    assert before.desired_on is True
    assert after_midnight.desired_on is True
    assert closed.desired_on is False


def test_dst_fall_back_window_stays_correct_across_the_transition():
    # 2026 US fall-back is November 1.
    sunset_for = _fixed_sunset(time(20, 0))
    before = compute_schedule(_dt(2026, 11, 1, 20, 30), sunset_for, 0, time(1, 0))
    after_midnight = compute_schedule(_dt(2026, 11, 2, 0, 30), sunset_for, 0, time(1, 0))
    closed = compute_schedule(_dt(2026, 11, 2, 1, 30), sunset_for, 0, time(1, 0))
    assert before.desired_on is True
    assert after_midnight.desired_on is True
    assert closed.desired_on is False


def test_no_stuck_state_across_a_clock_step():
    # A clock step (NTP correction) means the next tick's `now` can jump
    # arbitrarily. Since the function is stateless, a call far from any
    # previous one must still produce the locally-correct answer.
    sunset_for = _fixed_sunset(time(20, 0))
    jumped_forward = compute_schedule(_dt(2026, 9, 1, 21, 0), sunset_for, 0, time(23, 0))
    jumped_back = compute_schedule(_dt(2026, 1, 1, 19, 0), sunset_for, 0, time(23, 0))
    assert jumped_forward.desired_on is True
    assert jumped_back.desired_on is False


def test_polar_day_falls_back_instead_of_raising():
    def _polar(_d: date) -> datetime:
        raise PolarDayError("sun never sets")

    decision = compute_schedule(_dt(2026, 6, 21, 19, 0), _polar, 0, time(23, 0))
    assert decision.used_polar_fallback is True
    assert decision.on_time.tzinfo is not None
    assert decision.sunset is None  # no real sunset to report that day


def test_decision_reports_the_raw_computed_sunset():
    decision = compute_schedule(_dt(2026, 6, 1, 21, 0), _fixed_sunset(time(20, 0)), 45, time(23, 0))
    assert decision.sunset == _dt(2026, 6, 1, 20, 0)
    assert decision.on_time == _dt(2026, 6, 1, 20, 45)  # offset applied on top of the raw sunset


def test_decision_reports_sunset_even_for_an_invalid_window():
    decision = compute_schedule(_dt(2026, 6, 21, 10, 0), _fixed_sunset(time(21, 30)), 180, time(22, 0))
    assert decision.window_valid is False
    assert decision.sunset == _dt(2026, 6, 21, 21, 30)


def test_polar_day_fallback_still_produces_a_usable_window():
    def _polar(_d: date) -> datetime:
        raise PolarDayError("sun never sets")

    decision = compute_schedule(_dt(2026, 6, 21, 19, 0), _polar, 0, time(23, 0))
    assert decision.window_valid is True
    assert decision.desired_on is True  # 19:00 falls within the fallback [18:00, 23:00)


# -- next_transition_after (Story 10: manual override) ---------------------


def test_next_transition_before_on_time_is_on_time():
    nxt = next_transition_after(_dt(2026, 6, 1, 14, 0), _fixed_sunset(time(20, 0)), 0, time(23, 0))
    assert nxt == _dt(2026, 6, 1, 20, 0)


def test_next_transition_between_on_and_off_is_off_time():
    nxt = next_transition_after(_dt(2026, 6, 1, 21, 0), _fixed_sunset(time(20, 0)), 0, time(23, 0))
    assert nxt == _dt(2026, 6, 1, 23, 0)


def test_next_transition_after_off_time_is_tomorrows_on_time():
    nxt = next_transition_after(_dt(2026, 6, 1, 23, 30), _fixed_sunset(time(20, 0)), 0, time(23, 0))
    assert nxt == _dt(2026, 6, 2, 20, 0)


def test_next_transition_handles_a_midnight_crossing_window():
    # window 20:00 - 01:00(+1); at 22:00 the next boundary is tomorrow 01:00.
    nxt = next_transition_after(_dt(2026, 6, 1, 22, 0), _fixed_sunset(time(20, 0)), 0, time(1, 0))
    assert nxt == _dt(2026, 6, 2, 1, 0)


def test_next_transition_is_always_strictly_after_now():
    # Exactly at a boundary -- must return the *next* one, not the same instant.
    nxt = next_transition_after(_dt(2026, 6, 1, 20, 0), _fixed_sunset(time(20, 0)), 0, time(23, 0))
    assert nxt > _dt(2026, 6, 1, 20, 0)
    assert nxt == _dt(2026, 6, 1, 23, 0)
