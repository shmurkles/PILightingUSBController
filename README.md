# PILightingUSBController
A simple way to use a raspberry PI to turn on and off USB lights connected to a raspberry PI's USB ports depending on your local sunset sunrise times as they change throughout the year

## Power switching

The light is switched by cutting power to the Pi's built-in USB hub:

```bash
sudo uhubctl -l 2 -a off   # off
sudo uhubctl -l 2 -a on    # on
```

Verified working on the device. This is **ganged** — every port on hub location `2`
switches together — which is fine here because the light is the only USB device attached,
the Pi is reached over Pi Connect with no keyboard or mouse, and it boots from microSD.
Full rationale, the rejected alternatives, and the fallback if this ever stops working:
[docs/story-1-usb-power-spike.md](docs/story-1-usb-power-spike.md).

To record the hub listing and Pi/OS versions for the spike artefact:

```bash
sudo apt install -y uhubctl
sudo ./scripts/spike-usb-power.sh --no-cycle
```

## Controlling the light from Python

```python
from pilight.power import create_backend

backend = create_backend(config)   # backend chosen by config, not by a code edit
backend.set_power(True)            # on
backend.get_power()                # True | False | None (None = genuinely unknown)
```

Or by hand, to check the hardware:

```bash
sudo python3 -m pilight.power status
sudo python3 -m pilight.power off
sudo python3 -m pilight.power on
python3 -m pilight.power on --backend dryrun   # no hardware touched
```

Interface, config keys, error types, and how the service gets the privileges `uhubctl`
needs: [docs/power-backend.md](docs/power-backend.md).

## Sunset calculation

```python
from datetime import date
from pilight.sun import get_sunset

sunset = get_sunset(date.today(), lat=45.5152, lon=-122.6784, tz="America/Los_Angeles")
```

Pure arithmetic (the NOAA solar equations, via [`astral`](https://pypi.org/project/astral/))
-- no network call, ever. Verified against the NOAA Solar Calculator for Portland, OR on
all four solstices/equinoxes of 2026, within ±2 minutes; see `tests/test_sunset.py`.
Locations where the sun doesn't set that day raise `pilight.sun.PolarDayError` rather than
returning nonsense. Rationale: [RESEARCH.md §3](RESEARCH.md#3-how-do-we-compute-sunset-without-pinging-an-api).

## Location resolution

```python
from pathlib import Path
from pilight.location import resolve_location

location = resolve_location(Path("/var/lib/pilight/location.json"))
print(location.lat, location.lon, location.timezone, location.city, location.source)
```

Resolution order: a manual city pick always wins, then a permanent on-disk cache, then a
single one-time IP geolocation call, then (only if that's unreachable) an offline city
picker over the bundled `pilight/data/cities15000.tsv` (trimmed from
[GeoNames](https://www.geonames.org/), CC BY 4.0 -- see
[pilight/data/ATTRIBUTION.md](pilight/data/ATTRIBUTION.md)). After the first successful
resolution, no further network request happens unless the caller passes
`force_redetect=True`. Timezone is resolved separately and freshly on every call, system
setting first: rationale in [RESEARCH.md §2](RESEARCH.md#2-how-do-we-know-where-we-are-with-no-gps)
and [§4](RESEARCH.md#4-is-there-a-database-of-cities-for-sunset-lookup).

## Configuration file

```python
from pathlib import Path
from pilight.config import load_config, save_config

config = load_config(Path("/var/lib/pilight/config.json"))  # writes documented defaults on first run
config.offset_minutes   # -180..180, clamped on load; out-of-range values are logged and fixed
config.off_time         # "HH:MM"
config.location          # a pilight.location.ResolvedLocation, or None before first resolution
config.to_dict()         # directly usable as pilight.power.create_backend(config.to_dict())
```

One JSON file, read by the scheduler daemon and written by the GUI (Story 9). A missing file
gets documented defaults written to it immediately; a corrupt or unreadable one is logged
loudly and defaults are used for that run *without touching the file on disk* -- a bad config
must never leave the room dark all night, but it also shouldn't destroy whatever the user had.
Every field is validated independently, so one bad value can't take the rest of a working
config down with it. Writes are atomic (temp file + rename).

## Scheduler daemon

```python
from pathlib import Path
from pilight.scheduler import SchedulerDaemon

daemon = SchedulerDaemon(Path("/var/lib/pilight/config.json"))
daemon.run()   # loops forever: one reconciliation tick every 30s
```

Reconcile, don't fire: every tick, recompute what the light should be doing right now from
(now, config, sunset) and switch only on mismatch -- self-healing after reboot or power loss,
correct across DST and clock steps, applies config edits within 30s with no restart. The
decision itself, `pilight.scheduler.window.compute_schedule()`, is a pure function with no
I/O, so it's unit-tested exhaustively with frozen clocks rather than by running the daemon
for a day. An offset that pushes on-time past the configured off-time is detected as an
invalid window (logged, light left off) rather than switching on for the better part of a
day. Rationale: [RESEARCH.md §5](RESEARCH.md#5-scheduling-design-reconcile-dont-fire).

## Running as a service

```bash
sudo systemctl enable --now pilight-scheduler   # start now and on every boot
sudo systemctl status pilight-scheduler
sudo systemctl disable --now pilight-scheduler  # stop and remove from boot
journalctl -u pilight-scheduler -f              # every reconciliation decision and transition
```

Full install steps (dedicated venv, state directory permissions, seeding a location before
the service has anything to do): [docs/story-7-systemd-service.md](docs/story-7-systemd-service.md).
The unit file itself is [deploy/pilight-scheduler.service](deploy/pilight-scheduler.service).

## Tests

```bash
python3 -m pytest
```

No hub, no root, and no `uhubctl` required — the hardware is stubbed.

## Documents

- [EPIC.md](EPIC.md) — problem, architecture, and the twelve stories.
- [RESEARCH.md](RESEARCH.md) — the technical decisions behind them. Read before picking up a story.
