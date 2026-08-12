"""Pure formatting/snapping helpers for the GUI.

Kept separate from any Tkinter import so they're testable without a
display -- unlike app.py, which needs a real X session.
"""

from __future__ import annotations

from datetime import datetime

STEP_MINUTES = 15
OFFSET_MIN_MINUTES = -180
OFFSET_MAX_MINUTES = 180


def snap_to_step(minutes: float, step: int = STEP_MINUTES) -> int:
    """Round to the nearest ``step``-minute increment."""
    return round(minutes / step) * step


def format_offset(offset_minutes: int) -> str:
    """``-0:45``, ``+1:30``, ``0:00``."""
    sign = "-" if offset_minutes < 0 else ("+" if offset_minutes > 0 else "")
    hh, mm = divmod(abs(offset_minutes), 60)
    return f"{sign}{hh}:{mm:02d}"


def format_clock(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def off_time_choices(step: int = STEP_MINUTES) -> list[str]:
    """Every ``HH:MM`` in ``step``-minute increments across a day (96 for 15-min steps)."""
    return [f"{m // 60:02d}:{m % 60:02d}" for m in range(0, 24 * 60, step)]
