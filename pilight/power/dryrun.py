"""A backend that logs instead of switching, for development off-device."""

from __future__ import annotations

import logging

from .base import PowerBackend

log = logging.getLogger(__name__)


class DryRunBackend(PowerBackend):
    """Pretend to switch the light, and remember what was asked.

    Lets the scheduler, the GUI, and their tests run on a laptop with no hub
    attached. It reports state back faithfully, so a reconciliation loop driving
    it behaves exactly as it would against real hardware.
    """

    def __init__(self, initial_state: bool | None = False) -> None:
        self._state = initial_state
        self.calls: list[bool] = []  #: every set_power argument, in order, for tests

    def set_power(self, on: bool) -> None:
        self.calls.append(on)
        if on == self._state:
            log.debug("dry run: light already %s", _word(on))
        else:
            log.info("dry run: switching light %s", _word(on))
        self._state = on

    def get_power(self) -> bool | None:
        return self._state

    def describe(self) -> str:
        return "dry run (no hardware is switched)"


def _word(on: bool) -> str:
    return "on" if on else "off"
