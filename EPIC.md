# Epic: Sunset-Scheduled USB Light

## Problem

There is a USB light in the bedroom, plugged into a nearby Raspberry Pi. Turning it on
every evening and off every night by hand is a daily chore, and the right moment drifts by
about three hours across the year as sunset moves.

## Goal

The light turns itself on at a user-chosen offset from local sunset, and off at a
user-chosen clock time — every day, adjusting automatically as sunset shifts through the
year. A small native window on the Pi, reachable over Pi Connect, is the only interface
needed to change either setting.

## Success criteria

- Light switches on within 1 minute of `sunset + offset`, and off within 1 minute of the
  configured off time, every day, unattended.
- Correct behaviour continues across reboots, DST transitions, and network outages.
- No cloud service, API key, or scheduled internet request is required for daily operation.
- Changing a setting in the GUI takes effect within 30 seconds, with no restart.
- The whole UI is one window that fits comfortably in a Pi Connect viewport.

## Non-goals

- Dimming or colour control (the light is on/off only).
- Multiple lights, zones, or per-day schedules.
- Phone app, web UI, or remote access beyond what Pi Connect already provides.
- Motion sensing, presence detection, or any automation beyond the two configured times.

## Users

One user — the person in the room. Occasionally adjusts the offset; otherwise never
touches it.

## Architecture at a glance

```
┌────────────────────┐        writes         ┌──────────────────┐
│  GUI (Tkinter)     │ ────── config.json ──▶│  Scheduler       │
│  runs on demand    │                       │  daemon (systemd)│
│  offset + off-time │◀───── reads status ───│  30s reconcile   │
└────────────────────┘                       └────────┬─────────┘
         │                                            │
         │ reads                                      │ switches
         ▼                                            ▼
┌────────────────────┐                       ┌──────────────────┐
│ location cache     │                       │ power backend    │
│ city database      │                       │ uhubctl │ GPIO   │
│ sunset math        │                       └──────────────────┘
└────────────────────┘
```

Two processes, one JSON file between them. The daemon does all switching and runs whether
or not anyone is logged in; the GUI is a config editor that can be closed at any time.
Design rationale for each choice is in [RESEARCH.md](./RESEARCH.md) — **read it first**,
especially §1 (power switching) and §5 (reconcile, don't fire).

## Build order

| Milestone | Stories | Outcome |
|---|---|---|
| M1 — Can we switch it? | 1, 2 | Light turns on/off from a command |
| M2 — Does it know when? | 3, 4 | Correct sunset time for this location |
| M3 — Does it do it itself? | 5, 6, 7 | Unattended daily operation. **Solves the actual problem.** |
| M4 — Can I adjust it? | 8, 9 | The window over Pi Connect |
| M5 — Polish | 10, 11, 12 | Install, logs, override |

M3 is the real finish line; everything after it is convenience. If the project stalls,
it stalls having already solved the chore.

---

# Stories

## Story 1 — Spike: determine the USB power-cut mechanism

**As a** developer, **I need** to know how this specific Pi can cut power to the light,
**so that** the rest of the project is built against something real.

Timeboxed spike. USB power switching is a hub capability that many Pi models lack — see
RESEARCH.md §1 before starting. Nothing else should be built until this is answered.

**Acceptance criteria**
- [ ] `sudo uhubctl` output recorded in the story, including the Pi model and OS version.
- [ ] Determined whether the built-in hub supports per-port (`ppps`), ganged, or no switching.
- [ ] If switching exists, verified end-to-end: the light physically goes dark on command
      and comes back on.
- [ ] If ganged, confirmed what else loses power and whether that's acceptable
      (keyboard/mouse will die — only OK if the Pi is used headless via Pi Connect).
- [ ] A backend is chosen and written down: powered PPPS hub, GPIO + relay, or the Pi's
      own ports. Hardware ordered if needed.
- [ ] Light's current draw measured or looked up, and confirmed within the port's budget.

**Notes**
GPIO + relay (RESEARCH.md §1 option B) is the reliable escape hatch and costs about $5.
Take it early rather than fighting hub firmware.

---

## Story 2 — Power control backend

**As** the system, **I need** a single call that turns the light on or off, **so that**
scheduling logic never knows which hardware trick is underneath.

**Acceptance criteria**
- [ ] Interface: `set_power(on: bool)`, `get_power() -> bool | None` (`None` = unknown).
- [ ] Implementation for the backend chosen in Story 1.
- [ ] A `DryRunBackend` that logs instead of switching, for development off-device.
- [ ] Backend selected by config, not by code edit.
- [ ] Failures (hub unplugged, permission denied, `uhubctl` missing) raise a clear typed
      error and are logged — they never crash the daemon.
- [ ] Calling `set_power(True)` twice is harmless.
- [ ] Documented: how the service gets the privileges it needs (root via systemd, or a
      udev rule).

---

## Story 3 — Sunset calculation

**As** the system, **I need** today's sunset for a given location, **so that** the on-time
can be derived without any network call.

**Acceptance criteria**
- [ ] `get_sunset(date, lat, lon, tz) -> datetime` (timezone-aware), using `astral`.
- [ ] No network access, at any point, ever.
- [ ] Verified against the NOAA Solar Calculator for the real location on 4 dates
      (both solstices, both equinoxes) — within ±2 minutes.
- [ ] DST transition dates return correct local times.
- [ ] Polar "sun never sets" case raises a handled, documented exception rather than
      returning nonsense.

---

## Story 4 — Location resolution

**As a** user, **I want** the Pi to work out where it is on its own, **so that** I never
have to look up coordinates.

Resolution order: manual override → cached value → IP geolocation → offline city picker.
Accuracy needed is ~50 km; see RESEARCH.md §2 for why IP lookup is comfortably sufficient.

**Acceptance criteria**
- [ ] One-time IP geolocation on first run; result cached to disk permanently.
- [ ] No network request on any subsequent run unless the user asks to re-detect.
- [ ] GeoNames `cities15000` bundled, trimmed to name/country/lat/lon/timezone (~1 MB),
      with CC BY 4.0 attribution in the repo.
- [ ] Nearest-city lookup by haversine distance, completing in under ~200 ms.
- [ ] If the first run has no network, the user picks a city from the bundled list and
      that becomes the cached location.
- [ ] Manual city selection always overrides detection.
- [ ] Timezone resolved from system settings first, then IP result, then the city record.

---

## Story 5 — Configuration file

**As** both processes, **we need** one config file with a stable schema, **so that** the
GUI and daemon stay decoupled.

**Acceptance criteria**
- [ ] JSON at a documented path, with a `schema_version` field.
- [ ] Fields: sunset offset (minutes, −180…+180), off time (`HH:MM`), location
      (lat/lon/city/country/timezone/source), backend selection + its settings, manual
      override state.
- [ ] Missing file → written with documented defaults on first run.
- [ ] Corrupt or unparseable file → daemon logs loudly, falls back to defaults, and keeps
      running. A bad config must never leave the room dark all night.
- [ ] Writes are atomic (temp file + rename) so a half-written file is never read.
- [ ] Out-of-range values are clamped, and the clamp is logged.

---

## Story 6 — Scheduler daemon

**As a** user, **I want** the light to follow the schedule without anyone logged in,
**so that** it just works.

Implements the reconciliation loop from RESEARCH.md §5 — the core of the project.

**Acceptance criteria**
- [ ] Loop every 30 s: compute desired state, compare to actual, switch on mismatch.
- [ ] Desired state is a **pure function** of (now, config, sunset) and unit-tested in
      isolation with frozen clocks.
- [ ] Schedules crossing midnight work correctly (the normal case).
- [ ] Starting the daemon mid-window immediately switches the light **on** — this is the
      reboot-at-23:00 case and it must not wait for tomorrow.
- [ ] Config changes are picked up within 30 s without a restart.
- [ ] Empty/inverted window (offset pushes on-time past off-time) is detected, logged, and
      does not thrash the port.
- [ ] Backend errors are logged and retried on the next tick; the daemon does not exit.
- [ ] Survives NTP clock steps and DST transitions without a stuck state.

---

## Story 7 — systemd service

**As a** user, **I want** the scheduler running from boot, **so that** a power cut doesn't
end the arrangement.

**Acceptance criteria**
- [ ] Unit file that starts at boot with no login, with `Restart=always`.
- [ ] Logs go to the journal; `journalctl -u <service>` shows decisions and transitions.
- [ ] Runs with exactly the privileges the backend requires, and no more.
- [ ] Verified: full reboot → light is in the correct state within one loop interval.
- [ ] `enable` / `disable` / `status` documented in the README.

---

## Story 8 — Configuration window

**As a** user, **I want** a small dark window over Pi Connect, **so that** I can nudge the
timing without touching a terminal.

Target layout — one small, fixed-size, non-resizable window:

```
┌──────────────────────────────────────────┐
│  Bedroom Light                           │
│                                          │
│  Turn on, relative to sunset             │
│  −3h ├────────●────────┤ +3h             │
│           −0:45  ·  on at 19:38          │
│                                          │
│  Turn off at      [ 23:30  ▾ ]           │
│                                          │
│  ──────────────────────────────────────  │
│  Portland, US · sunset 20:23        ● on │
└──────────────────────────────────────────┘
```

**Acceptance criteria**
- [ ] Tkinter/`ttk`, dark colour scheme set explicitly (no reliance on a system theme).
- [ ] Slider: −3 h to +3 h, snapping to 15-minute steps, showing both the offset and the
      resulting clock time, updating live as it's dragged.
- [ ] Dropdown: off time in 15-minute increments.
- [ ] Corner status: nearest city and today's computed sunset time.
- [ ] Current light state shown.
- [ ] Window is small, fixed-size, and fully visible in a Pi Connect viewport without
      scrolling.
- [ ] Settings persist across restarts of the window.
- [ ] Warns visibly if the chosen combination produces an empty on-window.
- [ ] Readable and clickable over Pi Connect's screen sharing (verify on the device, not
      only on a desktop).

---

## Story 9 — GUI ↔ daemon wiring

**As a** user, **I want** my adjustment to take effect straight away, **so that** I can see
it worked.

**Acceptance criteria**
- [ ] GUI writes config atomically; daemon applies the change within 30 s.
- [ ] GUI reads and displays the daemon's current state and last transition.
- [ ] GUI runs unprivileged.
- [ ] GUI shows a clear "scheduler not running" state instead of pretending to work.
- [ ] Closing the GUI has no effect on the light.

---

## Story 10 — Manual override

**As a** user, **I want** to turn the light on or off right now, **so that** the schedule
isn't in charge on an unusual evening.

**Acceptance criteria**
- [ ] On/off control in the GUI, taking effect within one loop interval.
- [ ] Override holds until the next scheduled transition, then automatic control resumes.
- [ ] GUI clearly shows that an override is active and when it will lapse.
- [ ] Override state survives a daemon restart.

---

## Story 11 — Install & docs

**As a** user, **I want** a documented install, **so that** rebuilding the SD card isn't
an archaeology project.

**Acceptance criteria**
- [ ] Setup script or documented steps: dependencies, service install, first-run config.
- [ ] README covers hardware setup, the Story 1 spike result, install, and adjustment.
- [ ] Desktop launcher for the GUI so it's clickable in Pi Connect.
- [ ] Troubleshooting section: light won't switch, wrong sunset time, service not running.
- [ ] Verified end-to-end on a fresh Raspberry Pi OS image.

---

## Story 12 — Logging

**As a** developer, **I want** to see what the daemon decided and why, **so that** a wrong
evening can be diagnosed after the fact.

**Acceptance criteria**
- [ ] Every state transition logged with timestamp, computed sunset, on/off times, and reason.
- [ ] Resolved location and sunset logged at startup.
- [ ] Errors logged with enough context to identify the failing backend call.
- [ ] Log volume is sane — routine "no change" ticks are not logged at default level.

---

## Stretch

- **Sunrise-based off time.** Same slider, anchored to sunrise, for a wake-up light.
- **Fade.** Requires a dimmable light and PWM — out of scope for USB on/off.
- **Nudge memory.** If the user repeatedly overrides on at a consistent time, suggest
  adjusting the offset.

---

## Definition of done (per story)

- Acceptance criteria met and demonstrated on the actual Pi.
- Pure logic (schedule decisions, sunset math, config parsing) has unit tests.
- Failure modes log rather than crash.
- README updated if user-facing behaviour changed.
