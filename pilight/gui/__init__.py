"""The Tkinter configuration window -- Story 8.

    python -m pilight.gui

A config editor, not a controller (RESEARCH.md §6): writes pilight.config's
JSON file and can be closed at any time; pilight.scheduler's daemon owns all
actual switching.
"""

from .app import PiLightGUI
from .formatting import format_clock, format_offset, off_time_choices, snap_to_step

__all__ = [
    "PiLightGUI",
    "format_clock",
    "format_offset",
    "off_time_choices",
    "snap_to_step",
]
