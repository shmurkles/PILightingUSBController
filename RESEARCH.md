# Technical Research & Decisions

Answers to the open questions behind the epic. Read this before picking up any story.

---

## 1. How do we cut power to a USB port?

### The short version

USB port power switching is a **hub feature, not a Pi feature**. A USB hub may support
"per-port power switching" (PPPS); if it does, the host can send a `CLEAR_FEATURE
PORT_POWER` request and the hub physically cuts VBUS to that port. The tool that does
this from Linux is [`uhubctl`](https://github.com/mvp/uhubctl) (`apt install uhubctl`, or
build from source for the newest hub support).

The catch: **the built-in hub on most Raspberry Pi models either doesn't support this, or
supports it only in "ganged" mode** (all downstream ports switch together, not
individually). Support varies by model and has changed across hardware revisions, so this
must be verified on the actual device rather than assumed.

Roughly what to expect, in decreasing order of hope:

| Pi model | Built-in port power switching |
|---|---|
| Pi 1 B+ / Pi 2 B / Pi 3 B | Ganged — all 4 ports switch as one group |
| Pi 3 B+ | Ganged on some revisions, absent on others |
| Pi 4 B / 400 | Generally **not** supported (VL805 hub) |
| Pi 5 | Not reliably supported; verify |
| Pi Zero / Zero 2 W | Single OTG port, no switching |

**This is why Story 1 is a spike.** Run the check, then choose a backend. Do not write
scheduling code against an assumption here.

### The spike command

```bash
sudo apt install -y uhubctl
sudo uhubctl                      # lists hubs; look for "ppps" in the capability line
sudo uhubctl -l <location> -p <port> -a off   # try it with the light plugged in
```

A hub that reports `ppps` supports per-port switching. `ganged` means all-or-nothing.
Nothing at all means the hub can't switch power, and no software will make it.

### Backends, ranked

**A. Externally-powered USB hub with PPPS (recommended).**
Plug a supported hub into the Pi, plug the light into the hub, and switch that hub's port.
Works on *every* Pi model because it sidesteps the Pi's own hub entirely. It also gives
the light its own power budget instead of drawing from the Pi. `uhubctl`'s README
maintains a tested-compatible hub list — buy from that list, not from a marketplace
listing that merely claims "individual switches" (those are usually mechanical buttons,
which are useless to us). Cost: ~$20–40.

**B. GPIO + relay module or logic-level MOSFET (most reliable, cheapest).**
Cut the 5 V line of a USB extension cable, run it through a relay/MOSFET driven by a Pi
GPIO pin. Now "power" is a single `gpiozero` call and there is no hub-compatibility
question at all. Requires cutting a cable, which is the only real downside. Cost: ~$5.
This is the option to fall back to the moment the spike gets messy.

**C. Ganged switching on the Pi's own hub.**
Works if the spike says so, and costs nothing — but it kills **all** USB ports, including
a plugged-in keyboard and mouse. Acceptable only if the Pi is genuinely headless and
managed via Pi Connect / SSH. Treat as a bonus outcome, not the plan.

**D. Smart plug.** Rejected — adds a cloud dependency and a second device to solve a
problem we already have hardware for.

### Power draw caveat

Downstream USB on a Pi is current-limited (~1.2 A total across all ports on Pi 3/4). A
small USB LED strip or lamp is typically 0.2–0.5 A and fine. Measure before trusting it;
brownouts on a Pi look like random filesystem corruption, not like a lighting bug.

### Permissions

`uhubctl` needs raw USB access, i.e. root. Simplest path: run the scheduler daemon as
root via systemd. Tidier path: a `udev` rule granting the service user write access to
that specific hub device. Start with root, tighten later if it matters. The GUI never
needs privileges — it only writes a config file.

---

## 2. How do we know where we are, with no GPS?

Three mechanisms, used in this order:

**1. Manual override.** A city picked by the user always wins. This is the ground truth
and the escape hatch for everything below.

**2. IP geolocation, once, at first run.** A single HTTPS request to a free endpoint
(`ipapi.co/json`, `ip-api.com/json`, or `ipinfo.io/json`) returns lat/long/city/timezone.
Accuracy is city-level: typically 5–50 km. **That's far better than we need** — see the
error analysis below. Cache the result to disk permanently; re-query only on user request.
A home Pi does not move.

**3. Offline nearest-city fallback.** If there's no network at first run, present the
bundled city list and let the user pick. After that, no network is ever required again.

### Why not Wi-Fi positioning?

BSSID-based geolocation (scanning nearby access points and looking them up) is the classic
no-GPS trick, but it isn't viable here: Mozilla Location Service, the free option, was
shut down in 2024, and Google's Geolocation API needs an API key and a billing account.
For a device that needs ~50 km accuracy exactly once in its lifetime, IP lookup is the
right tool.

### Does location error matter?

Barely. Longitude error translates to sunset-time error at roughly **4 minutes per degree**
(~4 min per 111 km at the equator, less at higher latitudes). Latitude error affects sunset
seasonally, but at mid-latitudes a 50 km miss moves sunset by well under a minute for most
of the year. Total worst-case error from a bad IP lookup: a couple of minutes.

The UI's finest adjustment is **15 minutes**. The location error is invisible at that
resolution.

---

## 3. How do we compute sunset without pinging an API?

**With arithmetic.** Sunset is a solved astronomy problem — the NOAA Solar Calculator
equations take (date, latitude, longitude, timezone) and return sunrise/sunset accurate to
about **±1 minute** for latitudes between 72°N and 72°S. No network, no API key, no rate
limit, no failure mode where the light doesn't come on because a server was down.

**Decision: use the [`astral`](https://pypi.org/project/astral/) Python package.** It's
pure Python, has zero runtime dependencies, is packaged for Raspberry Pi OS, and implements
exactly these equations. Roughly:

```python
from astral import LocationInfo
from astral.sun import sun
from zoneinfo import ZoneInfo

loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz)
s = sun(loc.observer, date=today, tzinfo=ZoneInfo(tz))
sunset = s["sunset"]        # timezone-aware datetime
```

If we ever want zero dependencies, the NOAA equations are ~60 lines of trigonometry and can
be inlined — but there's no reason to start there.

**Which "sunset"?** The default is the moment the sun's upper limb touches the horizon
(90.833° zenith, which accounts for atmospheric refraction and the sun's angular radius).
The room actually gets dark somewhat later — that's precisely what the ±3 h offset slider
is for, so the user dials in their own preference rather than us guessing. If a user
consistently sits at +30 min, nothing is wrong; the design anticipated it.

### Do we need a precomputed table?

No. The calculation takes microseconds and runs a handful of times a day. Precomputing a
yearly table adds a cache-invalidation problem (what happens when the user moves, or picks
a new city?) in exchange for nothing. Compute on demand.

---

## 4. Is there a database of cities for sunset lookup?

Yes — but note that a city database is **not** how sunset gets calculated. Sunset comes
from the math above, which needs only lat/long. The city database serves two narrower
purposes: giving the user a human-readable "nearest city" label in the UI corner, and
providing a manual-picker fallback when there's no network.

**Decision: bundle [GeoNames](https://download.geonames.org/export/dump/) `cities15000`**
— every city over 15,000 population, ~25,000 rows, tab-separated, CC BY 4.0 licensed
(attribution required in the repo). Strip it at build time to the five columns we need —
name, country, latitude, longitude, timezone — which lands around 1 MB.

The timezone column is a quiet bonus: it means a manually-picked city carries its own
correct tz string, so we never have to ask the user for one.

Nearest-city lookup is a haversine distance over 25k rows — a few tens of milliseconds in
plain Python, run once at startup. No index, no spatial library, no cleverness required.

Use `cities5000` instead if "nearest city" keeps naming somewhere 40 km away and that feels
wrong. It's the same format, roughly twice the rows.

### Timezone handling

Prefer the **Pi's own system timezone** (`raspi-config` sets it; read it via
`zoneinfo`/`/etc/timezone`). It's almost always correct and it's what the user's clock
already shows. Fall back to the timezone from IP geolocation, then to the city database.
Store the tz string in config so the behaviour is explicit and debuggable.

DST is handled for free by computing in timezone-aware local time via `zoneinfo`. The
reconciliation-loop design (see below) makes DST jumps a non-event: the daemon re-derives
"what should the light be doing right now" every tick rather than arming a timer that a
clock shift could invalidate.

---

## 5. Scheduling design: reconcile, don't fire

The obvious implementation is a cron job or a timer that fires at sunset. **Don't.** It
breaks in all the ordinary ways: the Pi reboots after the on-event and the light stays off
all night; NTP steps the clock; DST shifts; the user changes the offset at 21:00 and
nothing happens until tomorrow.

Instead, the daemon runs a **state reconciliation loop**, every 30 seconds:

1. Read config (cheap; re-read on file mtime change so GUI edits apply within 30 s).
2. Compute today's `on_time = sunset + offset`.
3. Compute `off_time` from the configured clock time; if `off_time <= on_time`, it belongs
   to tomorrow (the schedule normally crosses midnight).
4. `desired = on_time <= now < off_time`.
5. If actual state ≠ desired, switch the port and log it.

This is idempotent, self-healing after reboot or power loss, correct across DST and clock
steps, and applies config changes almost immediately. It's also easier to test: the whole
decision is one pure function of (now, config, sunset).

### Edge cases it must handle

- **Interval wraps midnight** — the normal case, not the exception.
- **Offset pushes sunset past the off time** (e.g. +3 h in midsummer, off at 22:00, sunset
  21:30 → on at 00:30 tomorrow). The window is empty or nonsensical; the UI should warn
  rather than silently never turning on.
- **Manual override** — user flips the light by hand; honour it until the next scheduled
  transition, then resume automatic control.
- **Polar latitudes** — `astral` raises when the sun never sets. Catch it and fall back to
  a fixed clock time. Low priority, but it should log rather than crash.

---

## 6. GUI

**Decision: Tkinter with `ttk`.** It ships with Raspberry Pi OS (`python3-tk`), needs no
extra runtime, and renders fine over Pi Connect's screen sharing. GTK would look more
native and cost significantly more code for a two-control window.

Dark mode is manual — set explicit background/foreground colours and use `ttk.Style`
rather than hoping for a system theme. A fixed, small, non-resizable window is the target;
Pi Connect gives a modest viewport and a window that fits without scrolling is worth more
here than a flexible layout.

The GUI is a **config editor, not a controller**. It writes JSON and exits; the daemon owns
all switching. This keeps the light working whether or not anyone is logged in, which is
the entire point of the project.
