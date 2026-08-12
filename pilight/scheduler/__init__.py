"""The reconciliation loop -- Story 6.

Reconcile, don't fire: every tick, recompute what the light should be doing
right now and switch only on mismatch. Self-healing after reboot or power
loss, correct across DST and clock steps, applies config edits within one
tick. See RESEARCH.md §5 for why this beats a cron job or a fire-at-sunset
timer.

    from pilight.scheduler import SchedulerDaemon

    daemon = SchedulerDaemon(config_path)
    daemon.run()          # loops forever, one tick every 30s
    daemon.tick()          # or drive it one step at a time (what tests do)

The decision of "what should the light be doing right now" is a pure
function of (now, config, sunset) -- pilight.scheduler.window.compute_schedule
-- kept separate from the loop so it can be unit-tested with frozen clocks
and no daemon, backend, or filesystem involved.
"""

from .daemon import TICK_SECONDS, SchedulerDaemon
from .window import ScheduleDecision, compute_schedule, next_transition_after

__all__ = [
    "TICK_SECONDS",
    "ScheduleDecision",
    "SchedulerDaemon",
    "compute_schedule",
    "next_transition_after",
]
