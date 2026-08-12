"""The manual override value type -- Story 10.

Split out of model.py the same way pilight.location.ResolvedLocation is:
a small typed value the config schema embeds, not a schema of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class ManualOverride:
    """Force the light to a state, until the schedule's own next transition.

    ``until`` is computed once, when the override is set (see
    pilight.scheduler.window.next_transition_after) -- not recomputed every
    tick -- so "the next scheduled transition" means the one that was next
    *at the moment the user asked for this*, not a moving target.
    """

    state: bool  # True = forced on, False = forced off
    until: datetime  # tz-aware; the override no longer applies at/after this instant

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "until": self.until.isoformat()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ManualOverride:
        return cls(state=bool(data["state"]), until=datetime.fromisoformat(data["until"]))
