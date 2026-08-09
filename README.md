# PILightingUSBController
A simple way to use a raspberry PI to turn on and off USB lights connected to a raspberry PI's USB ports depending on your local sunset sunrise times as they change throughout the year

## Power switching

The light is switched by cutting power to the Pi's built-in USB hub:

```bash
sudo uhubctl -l 2 -a off   # off
sudo uhubctl -l 2 -a on    # on
```

This is **ganged** — every port on hub location `2` switches together, so the Pi must be
used headless (Pi Connect / SSH) and must not boot from a USB device. Full rationale, the
rejected alternatives, and the fallback if this stops working: [docs/story-1-usb-power-spike.md](docs/story-1-usb-power-spike.md).

To capture the spike evidence on the Pi:

```bash
sudo apt install -y uhubctl
sudo ./scripts/spike-usb-power.sh
```

## Documents

- [EPIC.md](EPIC.md) — problem, architecture, and the twelve stories.
- [RESEARCH.md](RESEARCH.md) — the technical decisions behind them. Read before picking up a story.
