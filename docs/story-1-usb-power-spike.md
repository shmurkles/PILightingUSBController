# Story 1 — Spike: USB power-cut mechanism

**Status:** decision made, on-device evidence pending
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
Pi's built-in hub. No extra hardware is bought.

This is option C in RESEARCH.md §1, described there as "a bonus outcome, not the plan" —
it is acceptable here only because the Pi is used headless over Pi Connect, so there is no
keyboard or mouse on those ports to kill. The moment a peripheral that matters is plugged
into that hub, this backend stops being viable and the fallback is option B (GPIO + relay,
~$5).

### Consequences accepted

- **All ports on location `2` go dark together.** Anything else plugged into that hub loses
  power for the whole on-window, not just the light.
- **The Pi must not boot from USB.** Cutting the hub cuts the boot device. `scripts/spike-usb-power.sh`
  refuses to run the power cycle if the root filesystem is on a USB device; do not override
  that check on this machine — switch to backend B instead.
- **Root is required.** `uhubctl` needs raw USB access. Per RESEARCH.md §1, the scheduler
  daemon runs as root under systemd (Story 7); the GUI stays unprivileged because it only
  writes JSON.
- **No per-port granularity, ever.** Story 2's `set_power(on: bool)` is a whole-hub
  operation. The interface hides this, but the config must record which hub location is
  being switched so the behaviour is explicit.

### Rejected

| Option | Why not |
|---|---|
| A — powered PPPS hub | Costs $20–40 and solves a problem we don't have; the built-in hub already switches. |
| B — GPIO + relay | Held in reserve. Take it if the ganged blast radius ever becomes a problem or if the hub firmware misbehaves. |
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

---

## Evidence

Run on the Pi, with the light plugged in:

```bash
sudo ./scripts/spike-usb-power.sh
```

It records the Pi model, OS and kernel versions, the full `uhubctl` listing, and the
result of an off/on cycle, then writes a report to `docs/story-1-spike-results.md`. Commit
that file — it is the artefact the acceptance criteria ask for.

Read the capability line for location `2` in the output. `ganged` confirms the decision
above. If it unexpectedly says `ppps`, that is *better* news: switch to a single port with
`-p <n>`, set `ports` in the config, and the blast radius disappears.

### Acceptance criteria

- [ ] `sudo uhubctl` output recorded, including Pi model and OS version — run the script.
- [ ] Per-port vs ganged vs none determined — expected `ganged`; confirm from the output.
- [x] Backend chosen and written down — `uhubctl`, ganged, location `2`. No hardware to order.
- [ ] Verified end-to-end: light goes dark on command and comes back — the script's cycle step.
- [ ] Ganged blast radius confirmed acceptable — script lists what else is on the hub;
      confirm nothing there matters.
- [ ] Light's current draw measured or looked up, within budget — the script prompts for it.
      Budget is ~1.2 A shared across all downstream ports on Pi 3/4; a USB lamp is typically
      0.2–0.5 A. Brownouts present as filesystem corruption, not as a lighting bug, so do
      not skip this.

The three unchecked boxes that need hands on hardware are the whole remaining cost of this
story. Everything else is settled.
