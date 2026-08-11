# Story 1 — spike results

Generated 2026-08-10 by re-running the Story 1 spike over an SSH session (Tailscale),
with the physical off/on observation done by the device owner in chat rather than at
the keyboard — `scripts/spike-usb-power.sh` prompts interactively via `/dev/tty` and
can't run unattended over a plain SSH pipe, so the same checks were done by hand.
Decision and rationale live in [story-1-usb-power-spike.md](./story-1-usb-power-spike.md).

| | |
|---|---|
| Pi model | Raspberry Pi 4 Model B Rev 1.5 |
| OS | Debian GNU/Linux 13 (trixie) |
| Kernel | Linux 6.18.34+rpt-rpi-v8 aarch64 |
| uhubctl | 2.6.0-1 |
| Hub location switched | `2` |
| Switching mode | `ppps` (hardware is per-port capable) — operated ganged (`-a off`/`-a on`, no `-p`), since the light is the only thing attached |
| Root filesystem | `/dev/mmcblk0p2` (microSD) — not USB, so the ganged cut cannot take the boot device down |
| End-to-end power cycle | verified end-to-end — light went dark on `off` and returned on `on` |
| Light current draw | not precisely measured — LED fairy lights, no rating label found; owner's rough upper-bound estimate is "well under 10 W" |

Budget is ~1.2 A shared across all downstream ports on Pi 3/4. LED fairy lights typically
draw well under 0.5 A in practice, so this is expected to be comfortably within budget, but
the number above is an estimate, not a measurement — worth confirming with a USB power
meter if the project ever adds a second bus-powered device.

## `uhubctl` listing (idle, before the test)

```
Current status for hub 2 [1d6b:0003 Linux 6.18.34+rpt-rpi-v8 xhci-hcd xHCI Host Controller 0000:01:00.0, USB 3.00, 4 ports, ppps]
  Port 1: 02a0 power 5gbps Rx.Detect
  Port 2: 02a0 power 5gbps Rx.Detect
  Port 3: 02a0 power 5gbps Rx.Detect
  Port 4: 02a0 power 5gbps Rx.Detect
Current status for hub 1-1 [2109:3431 USB2.0 Hub, USB 2.10, 4 ports, ppps]
  Port 1: 0100 power
  Port 2: 0100 power
  Port 3: 0100 power
  Port 4: 0100 power
Current status for hub 1 [1d6b:0002 Linux 6.18.34+rpt-rpi-v8 xhci-hcd xHCI Host Controller 0000:01:00.0, USB 2.00, 1 ports, ppps]
  Port 1: 0507 power highspeed suspend enable connect [2109:3431 USB2.0 Hub, USB 2.10, 4 ports, ppps]
```

Hub `1-1` (the USB2 companion path for the same physical connectors) switches together
with hub `2` under `uhubctl -l 2 -a off/on` — both are reported and toggled in the same
call, which matches the "whole hub" behaviour Story 2's backend assumes.

## Devices on the bus at spike time

```
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 002: ID 2109:3431 VIA Labs, Inc. Hub
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
```

The light itself doesn't enumerate as a distinct USB device — consistent with a bus-powered
light that has no data chip, only a power draw on the port it's plugged into (one of the
Pi's own USB3 ports, feeding through hub `2`).
