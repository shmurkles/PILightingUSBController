# Story 1 — Spike: USB power-cut mechanism

**Status:** answered — switching verified on the device
**Backend chosen:** `uhubctl`, ganged, on the Pi's own hub (RESEARCH.md §1, option **C**)
**Switch command:**

```bash
sudo uhubctl -l 2 -a off   # light off
sudo uhubctl -l 2 -a on    # light on
```

Note the absence of `-p`: this addresses *all* ports on hub location `2` as one group. That
is the defining property of this backend and everything below follows from it.

---

## Decision

The light is switched by cutting power to every downstream port of hub location `2` on the
Pi's built-in hub. This has been tried on the actual device: the light goes dark on `off`
and comes back on `on`. No extra hardware is needed and none was bought.

This is option C in RESEARCH.md §1, described there as "a bonus outcome, not the plan." It
is the right call here: the Pi is accessed entirely over Pi Connect with no keyboard or
mouse attached, and the LED light is the only thing plugged into USB. The ganged blast
radius covers exactly one device — the one we want to switch.

### Consequences accepted

- **All ports on location `2` go dark together.** Today that set is just the light, so the
  distinction is academic. It stops being academic the moment something else is plugged in
  for the duration of an on-window; at that point the fallback is option B (GPIO + relay,
  ~$5).
- **Boot device is safe.** This Pi boots from microSD, not USB, so cutting the hub cannot
  take the root filesystem down with the light. This is a real hazard on a USB-booting Pi,
  so `scripts/spike-usb-power.sh` checks for it — the check simply passes here, and it
  protects anyone who later rebuilds this project on a USB-booting machine.
- **Root is required.** `uhubctl` needs raw USB access. Per RESEARCH.md §1, the scheduler
  daemon runs as root under systemd (Story 7); the GUI stays unprivileged because it only
  writes JSON.
- **No per-port granularity.** Story 2's `set_power(on: bool)` is a whole-hub operation.
  The interface hides this, but the config records which hub location is switched so the
  behaviour stays explicit.

### Rejected

| Option | Why not |
|---|---|
| A — powered PPPS hub | Costs $20–40 and solves a problem we don't have; the built-in hub already switches. |
| B — GPIO + relay | Held in reserve. Take it if the ganged blast radius becomes a problem or the hub firmware misbehaves. |
| D — smart plug | Cloud dependency, second device. Rejected in RESEARCH.md. |

---

## Configuration this implies for Story 2

```json
{
  "backend": "uhubctl",
  "uhubctl": {
    "location": "2",
    "ports": null
  }
}
```

`ports: null` means ganged — the backend omits `-p` entirely. Keeping the field present
(rather than absent) leaves room for a per-port hub later without a schema bump.

Two behaviours Story 2 inherits directly from this spike:

- `set_power(True)` twice must be harmless. `uhubctl -a on` on an already-on hub is a no-op,
  so this comes free, but the backend should not assume it and should still be idempotent
  at its own level.
- `get_power()` can read real state back via `uhubctl -l 2` rather than trusting a cached
  flag, which is what makes the Story 6 reconciliation loop self-healing after a reboot.

---

## Acceptance criteria

- [x] Backend chosen and written down — `uhubctl`, ganged, location `2`. No hardware ordered.
- [x] Per-port vs ganged vs none determined — ganged (`-l 2` with no `-p`, switching the
      whole hub).
- [x] Verified end-to-end — the light physically goes dark on command and comes back on.
- [x] Ganged blast radius confirmed acceptable — the light is the only USB device attached,
      the Pi is reached over Pi Connect with no keyboard or mouse, and it boots from microSD.
- [ ] `sudo uhubctl` output recorded, with Pi model and OS version — the switching works,
      but the listing itself is not yet in the repo.
- [ ] Light's current draw measured or looked up, and confirmed within budget — see below.

### Capturing the last two

```bash
sudo ./scripts/spike-usb-power.sh --no-cycle
```

Records the Pi model, OS and kernel versions, the full `uhubctl` listing and its capability
line for location `2`, the devices on the bus, and a prompt for the light's current draw.
Writes `docs/story-1-spike-results.md` — commit that as the artefact. `--no-cycle` skips the
off/on test, since that part is already confirmed; drop the flag to re-run it.

**Current draw is the one that still carries risk.** Downstream USB on a Pi is limited to
roughly 1.2 A total across all ports (Pi 3/4); a USB lamp or LED strip is typically
0.2–0.5 A and fine. Worth checking the label, because a brownout on a Pi presents as random
filesystem corruption rather than as a lighting bug — it would be diagnosed as anything but
this project.

Neither open item blocks Story 2. The interface, the command, and the ganged semantics are
all settled.
