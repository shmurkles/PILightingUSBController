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

## Tests

```bash
python3 -m pytest
```

No hub, no root, and no `uhubctl` required — the hardware is stubbed.

## Documents

- [EPIC.md](EPIC.md) — problem, architecture, and the twelve stories.
- [RESEARCH.md](RESEARCH.md) — the technical decisions behind them. Read before picking up a story.
