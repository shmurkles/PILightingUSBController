"""compute_schedule(): the whole scheduling decision, as one pure function.

No I/O, no clock reads, no logging -- everything it needs comes in as an
argument, which is what lets it be unit-tested exhaustively with frozen
clocks (Story 6's own acceptance criterion) instead of only being exercised
by running the real daemon for a day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable

from pilight.sun import PolarDayError

#: A window longer than this is treated as a misconfiguration (offset pushed
#: on-time past a sane off-time) rather than an unusually long evening -- see
#: RESEARCH.md §5's "offset pushes sunset past the off time" edge case.
MAX_SANE_WINDOW_HOURS = 20.0

#: Used only if the sun genuinely never sets/rises this date at this
#: latitude (astral's PolarDayError) -- a fixed fallback so the schedule
#: still does *something* sane rather than crashing. Low priority; see
#: RESEARCH.md §5.
POLAR_FALLBACK_ON_TIME = time(18, 0)

SunsetLookup = Callable[[date], datetime]


@dataclass(frozen=True)
class ScheduleDecision:
    """What the light should be doing right now, and why."""

    desired_on: bool
    on_time: datetime
    off_time: datetime
    window_valid: bool
    reason: str | None = None
    used_polar_fallback: bool = False


def _on_time_for(
    anchor_date: date, sunset_for_date: SunsetLookup, offset_minutes: int, tz
) -> tuple[datetime, bool]:
    try:
        sunset = sunset_for_date(anchor_date)
    except PolarDayError:
        fallback = datetime.combine(anchor_date, POLAR_FALLBACK_ON_TIME, tzinfo=tz)
        return fallback, True
    return sunset + timedelta(minutes=offset_minutes), False


def _window_for(
    anchor_date: date, sunset_for_date: SunsetLookup, offset_minutes: int, off_time: time, tz
) -> tuple[datetime, datetime, bool]:
    on_time, used_fallback = _on_time_for(anchor_date, sunset_for_date, offset_minutes, tz)
    off = datetime.combine(on_time.date(), off_time, tzinfo=on_time.tzinfo)
    if off <= on_time:
        off += timedelta(days=1)
    return on_time, off, used_fallback


def compute_schedule(
    now: datetime,
    sunset_for_date: SunsetLookup,
    offset_minutes: int,
    off_time: time,
    *,
    tz=None,
    max_window_hours: float = MAX_SANE_WINDOW_HOURS,
) -> ScheduleDecision:
    """What should the light be doing at ``now``?

    Considers two candidate windows -- anchored to today's sunset and to
    yesterday's -- because a window that crosses midnight (the normal case)
    can still be active after midnight today even though it started
    "yesterday" by calendar date. At most one is ever active at a given
    instant in ordinary configurations.

    Args:
        now: tz-aware instant to evaluate.
        sunset_for_date: pure lookup, e.g. a closure over
            ``pilight.sun.get_sunset`` bound to a location. May raise
            :class:`~pilight.sun.PolarDayError`, handled by falling back to
            :data:`POLAR_FALLBACK_ON_TIME`.
        offset_minutes: on-time = sunset + this many minutes.
        off_time: the configured clock time the light goes off.
        tz: timezone for the polar-fallback on-time. Defaults to ``now``'s
            own tzinfo, which is correct for every real caller (the location
            whose sunset feeds ``sunset_for_date`` is the same location
            ``now`` is being evaluated in); only tests that want to force
            the fallback path independently of ``now`` need to override it.
        max_window_hours: a resulting window longer than this is treated as
            a misconfiguration rather than an unusually long evening.

    Returns:
        A :class:`ScheduleDecision`. When ``window_valid`` is ``False``,
        ``desired_on`` is always ``False`` -- see RESEARCH.md §5: an
        offset that pushes on-time past the configured off-time produces a
        near-24h window, and turning the light on almost permanently is a
        worse failure than not turning it on at all while the
        misconfiguration gets noticed and fixed.
    """
    tz = tz if tz is not None else now.tzinfo
    today = now.date()
    on_today, off_today, fallback_today = _window_for(
        today, sunset_for_date, offset_minutes, off_time, tz
    )
    on_yesterday, off_yesterday, _ = _window_for(
        today - timedelta(days=1), sunset_for_date, offset_minutes, off_time, tz
    )

    duration = off_today - on_today
    window_valid = timedelta(0) < duration <= timedelta(hours=max_window_hours)

    if not window_valid:
        return ScheduleDecision(
            desired_on=False,
            on_time=on_today,
            off_time=off_today,
            window_valid=False,
            reason=(
                f"window is {duration} long (on={on_today.time()}, off={off_today.time()}); "
                f"offset likely pushes on-time past a sane off-time"
            ),
            used_polar_fallback=fallback_today,
        )

    desired = (on_today <= now < off_today) or (on_yesterday <= now < off_yesterday)
    return ScheduleDecision(
        desired_on=desired,
        on_time=on_today,
        off_time=off_today,
        window_valid=True,
        used_polar_fallback=fallback_today,
    )


def next_transition_after(
    now: datetime,
    sunset_for_date: SunsetLookup,
    offset_minutes: int,
    off_time: time,
    *,
    tz=None,
) -> datetime:
    """The next moment compute_schedule()'s own decision would change, strictly after ``now``.

    Used by the manual override (Story 10): an override set right now holds
    until this moment, then automatic control resumes -- by construction,
    that's exactly when the schedule's own desire changes, so the handoff
    is seamless regardless of which direction the override forced.

    Looks at yesterday's, today's, and tomorrow's sunset-anchored windows and
    returns the smallest on/off boundary strictly after ``now`` -- three
    windows is enough margin that "now" being anywhere in a normal-length
    window still finds its close, and the window after it, without needing
    to search further.
    """
    tz = tz if tz is not None else now.tzinfo
    candidates: list[datetime] = []
    for offset_days in (-1, 0, 1):
        on, off, _ = _window_for(now.date() + timedelta(days=offset_days), sunset_for_date, offset_minutes, off_time, tz)
        candidates.extend((on, off))
    return min(t for t in candidates if t > now)
