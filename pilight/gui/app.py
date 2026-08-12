"""PiLightGUI -- the Tkinter configuration window (Story 8/9).

A config editor, not a controller (RESEARCH.md §6): it writes pilight.config's
JSON file on every change and can be closed at any time. It never calls a
power backend directly -- pilight.scheduler's daemon owns all actual
switching, which is what keeps the light working whether or not this window
is open.

The slider/dropdown preview (the on-time readout and the empty-window
warning) is always computed locally from whatever is currently selected, via
pilight.scheduler.window.compute_schedule() -- it answers "what would this
setting do", independent of the daemon.

The status row is different: it reads pilight.status's status file, written
by the daemon every successful tick (Story 9). A *fresh* file means real
actual state and real last-transition history, not a GUI-side guess -- this
is what an unprivileged process can show without ever touching uhubctl
directly. A *missing or stale* file means the daemon isn't keeping up (or
isn't running at all), and that's shown as such rather than silently
displaying the last thing it happened to say.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
from tkinter import ttk
from typing import Callable

from pilight.config import PiLightConfig, load_config, save_config
from pilight.scheduler.window import compute_schedule
from pilight.status import load_status
from pilight.sun import get_sunset

from .formatting import (
    OFFSET_MAX_MINUTES,
    OFFSET_MIN_MINUTES,
    format_clock,
    format_offset,
    off_time_choices,
    snap_to_step,
)

BG = "#1e1e1e"
PANEL = "#2a2a2a"
FG = "#e8e8e8"
MUTED = "#9a9a9a"
ACCENT = "#4fa8ff"
ON_COLOR = "#57c785"
OFF_COLOR = "#707070"
UNKNOWN_COLOR = "#9a9a9a"
NOT_RUNNING_COLOR = "#e0a030"
WARN_COLOR = "#e0a030"

WINDOW_TITLE = "Bedroom Light"
WINDOW_SIZE = "440x290"

REFRESH_INTERVAL_MS = 60_000


def _parse_off_time(value: str) -> time:
    return time.fromisoformat(value)


class PiLightGUI:
    def __init__(
        self,
        config_path: Path,
        *,
        status_path: Path | None = None,
        root: tk.Tk | None = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        get_sunset_fn: Callable[..., datetime] = get_sunset,
    ):
        self.config_path = config_path
        self._status_path = status_path or config_path.with_name("status.json")
        self._now_fn = now_fn
        self._get_sunset_fn = get_sunset_fn
        self.config: PiLightConfig = load_config(config_path)

        self.root = root or tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(False, False)
        self.root.configure(background=BG)

        self._build_style()
        self._build_widgets()
        self._refresh()
        self.root.after(REFRESH_INTERVAL_MS, self._tick_refresh)

    def run(self) -> None:
        self.root.mainloop()

    def destroy(self) -> None:
        self.root.destroy()

    # -- widget construction -------------------------------------------------

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TSeparator", background=PANEL)
        style.configure("Horizontal.TScale", background=BG, troughcolor=PANEL)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", PANEL)],
            foreground=[("readonly", FG)],
            selectbackground=[("readonly", PANEL)],
            selectforeground=[("readonly", FG)],
        )
        # ttk.Style doesn't reach the Combobox popdown listbox -- it's a
        # separate legacy Tk widget under the hood.
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", BG)

    def _build_widgets(self) -> None:
        pad = {"padx": 16}

        ttk.Label(self.root, text=WINDOW_TITLE, font=("TkDefaultFont", 14, "bold")).pack(
            anchor="w", pady=(16, 8), **pad
        )
        ttk.Label(self.root, text="Turn on, relative to sunset").pack(anchor="w", **pad)

        slider_row = ttk.Frame(self.root)
        slider_row.pack(fill="x", **pad)
        ttk.Label(slider_row, text="-3h", foreground=MUTED).pack(side="left")
        # No `command=` yet: .set() below would otherwise queue a Tcl-level
        # callback into _on_offset_change -> _refresh() before the widgets
        # _refresh() touches (on_time_label etc., built further down) exist.
        # That callback fires on the next real event-loop pump, not
        # synchronously -- invisible to any test that never runs one, which
        # is exactly how this shipped once already.
        self.offset_scale = ttk.Scale(
            slider_row, from_=OFFSET_MIN_MINUTES, to=OFFSET_MAX_MINUTES, orient="horizontal"
        )
        self.offset_scale.set(self.config.offset_minutes)
        self.offset_scale.configure(command=self._on_offset_change)
        self.offset_scale.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(slider_row, text="+3h", foreground=MUTED).pack(side="left")

        self.on_time_label = ttk.Label(self.root, foreground=MUTED)
        self.on_time_label.pack(anchor="center", pady=(0, 8))

        off_row = ttk.Frame(self.root)
        off_row.pack(fill="x", pady=(4, 4), **pad)
        ttk.Label(off_row, text="Turn off at").pack(side="left")
        self.off_time_var = tk.StringVar(value=self.config.off_time)
        self.off_time_combo = ttk.Combobox(
            off_row,
            textvariable=self.off_time_var,
            values=off_time_choices(),
            state="readonly",
            width=8,
        )
        self.off_time_combo.pack(side="right")
        self.off_time_combo.bind("<<ComboboxSelected>>", self._on_off_time_change)

        self.warning_label = ttk.Label(self.root, foreground=WARN_COLOR, wraplength=400)
        self.warning_label.pack(anchor="w", pady=(4, 0), **pad)

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", pady=(12, 8), **pad)

        status_row = ttk.Frame(self.root)
        status_row.pack(fill="x", pady=(0, 2), **pad)
        self.corner_label = ttk.Label(status_row, foreground=MUTED)
        self.corner_label.pack(side="left")
        status_right = ttk.Frame(status_row)
        status_right.pack(side="right")
        self.status_dot = ttk.Label(status_right, text="●")
        self.status_dot.pack(side="left")
        self.status_text = ttk.Label(status_right, text="")
        self.status_text.pack(side="left", padx=(4, 0))

        self.transition_label = ttk.Label(self.root, foreground=MUTED, font=("TkDefaultFont", 8))
        self.transition_label.pack(anchor="e", pady=(0, 12), **pad)

    # -- callbacks -------------------------------------------------------------

    def _on_offset_change(self, raw_value: str) -> None:
        raw = float(raw_value)
        snapped = int(snap_to_step(raw))
        snapped = max(OFFSET_MIN_MINUTES, min(OFFSET_MAX_MINUTES, snapped))
        if abs(raw - snapped) > 1e-6:
            self.offset_scale.set(snapped)  # re-invokes this callback, already snapped
            return
        if snapped != self.config.offset_minutes:
            self.config = replace(self.config, offset_minutes=snapped)
            save_config(self.config_path, self.config)
        self._refresh()

    def _on_off_time_change(self, _event: object = None) -> None:
        value = self.off_time_var.get()
        if value != self.config.off_time:
            self.config = replace(self.config, off_time=value)
            save_config(self.config_path, self.config)
        self._refresh()

    def _tick_refresh(self) -> None:
        self._refresh()
        self.root.after(REFRESH_INTERVAL_MS, self._tick_refresh)

    # -- derived display ---------------------------------------------------

    def _refresh(self) -> None:
        offset_text = format_offset(self.config.offset_minutes)
        location = self.config.location

        if location is None:
            self.on_time_label.configure(text=f"{offset_text} · location not yet resolved")
            self.warning_label.configure(text="")
            self.status_dot.configure(foreground=MUTED)
            self.status_text.configure(text="unknown")
            self.transition_label.configure(text="")
            self.corner_label.configure(
                text="location not yet resolved (run: python -m pilight.location resolve)"
            )
            return

        def sunset_for(d: date) -> datetime:
            return self._get_sunset_fn(d, lat=location.lat, lon=location.lon, tz=location.timezone)

        now = self._now_fn()
        decision = compute_schedule(
            now, sunset_for, self.config.offset_minutes, _parse_off_time(self.config.off_time)
        )

        self.on_time_label.configure(
            text=f"{offset_text} · on at {format_clock(decision.on_time)}"
        )

        if decision.window_valid:
            self.warning_label.configure(text="")
        else:
            self.warning_label.configure(text="⚠ This combination never turns the light on")

        sunset_today = sunset_for(now.date())
        self.corner_label.configure(
            text=f"{location.city}, {location.country} · sunset {format_clock(sunset_today)}"
        )

        self._refresh_status(now)

    def _refresh_status(self, now: datetime) -> None:
        status = load_status(self._status_path)

        if status is None or status.is_stale(now=now):
            self.status_dot.configure(foreground=NOT_RUNNING_COLOR)
            self.status_text.configure(text="scheduler not running")
            self.transition_label.configure(
                text="no data from the scheduler yet" if status is None else "last known state is stale"
            )
            return

        if status.actual_on is None:
            self.status_dot.configure(foreground=UNKNOWN_COLOR)
            self.status_text.configure(text="unknown")
        elif status.actual_on:
            self.status_dot.configure(foreground=ON_COLOR)
            self.status_text.configure(text="on")
        else:
            self.status_dot.configure(foreground=OFF_COLOR)
            self.status_text.configure(text="off")

        if status.last_transition_at is None:
            self.transition_label.configure(text="no transitions recorded yet")
        else:
            direction = "on" if status.last_transition_to else "off"
            self.transition_label.configure(
                text=f"last transition: {direction} at {format_clock(status.last_transition_at)}"
            )
