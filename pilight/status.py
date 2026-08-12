"""The daemon status file -- Story 9.

The scheduler daemon (root) writes this every successful tick; the GUI
(unprivileged) reads it to show the *real* current state and last
transition, rather than recomputing an approximation (Story 8's interim
behaviour) or -- worse -- querying the power backend directly, which an
unprivileged process can't do for the uhubctl backend.

    from pilight.status import load_status, save_status

Freshness, not just presence, is what tells "scheduler not running" from
"scheduler running and reporting a real state" -- see is_stale() and
Story 9's own acceptance criterion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pilight.util.atomic import atomic_write_text

#: A status file older than this is treated as "scheduler not running"
#: rather than trusted -- generous relative to the 30s tick interval so
#: ordinary tick-to-tick jitter never flickers the GUI's own display.
STALE_AFTER_SECONDS = 90.0


@dataclass(frozen=True)
class DaemonStatus:
    actual_on: bool | None
    desired_on: bool
    last_transition_at: datetime | None
    last_transition_to: bool | None
    updated_at: datetime

    def is_stale(self, *, now: datetime | None = None, stale_after: float = STALE_AFTER_SECONDS) -> bool:
        now = now if now is not None else datetime.now().astimezone()
        return (now - self.updated_at).total_seconds() > stale_after

    def to_dict(self) -> dict:
        return {
            "actual_on": self.actual_on,
            "desired_on": self.desired_on,
            "last_transition_at": (
                self.last_transition_at.isoformat() if self.last_transition_at else None
            ),
            "last_transition_to": self.last_transition_to,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> DaemonStatus:
        return cls(
            actual_on=data["actual_on"],
            desired_on=data["desired_on"],
            last_transition_at=(
                datetime.fromisoformat(data["last_transition_at"])
                if data.get("last_transition_at")
                else None
            ),
            last_transition_to=data.get("last_transition_to"),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


def load_status(path: Path) -> DaemonStatus | None:
    """The current status, or ``None`` if there isn't one yet or it's unreadable.

    Never raises: a missing or corrupt status file just means the GUI falls
    back to treating the scheduler as not running, which is the safe read
    in both cases.
    """
    try:
        return DaemonStatus.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_status(path: Path, status: DaemonStatus) -> None:
    atomic_write_text(path, json.dumps(status.to_dict(), indent=2) + "\n")
