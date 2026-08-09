# Power control backend (Story 2)

One call turns the light on or off. The scheduler never learns whether that means a USB
hub, a relay, or a log line.

```python
from pilight.power import create_backend

backend = create_backend(config)   # chosen by config, never by a code edit
backend.set_power(True)            # on
backend.get_power()                # True | False | None
```

## Interface

| Method | Contract |
|---|---|
| `set_power(on: bool) -> None` | Switch the light. Idempotent — calling it twice with the same value is the normal case, not an error. |
| `get_power() -> bool \| None` | `True` on, `False` off, `None` genuinely unknown. |
| `describe() -> str` | One line for the startup log: `uhubctl hub 2 (ganged, all ports)`. |

`None` means **unknown**, never off. A caller that collapses it to `False` will switch the
light at the wrong moment. It comes up when a per-port hub reports its ports disagreeing,
or when output can't be parsed — the question was asked and the answer was ambiguous. When
the question can't be asked at all, you get an exception instead.

`set_power` deliberately does **not** read state back to confirm the switch. The Story 6
reconciliation loop compares desired against actual every 30 s, so a silently failed switch
is caught on the next tick anyway — and a read-back would add a second command per
transition plus a class of false failures on hubs that report stale status.

## Configuration

```json
{
  "backend": "uhubctl",
  "uhubctl": {
    "location": "2",
    "ports": null,
    "binary": "uhubctl",
    "sudo": false,
    "timeout_seconds": 10.0
  },
  "dryrun": { "initial_state": false }
}
```

| Key | Meaning |
|---|---|
| `backend` | `uhubctl` or `dryrun`. Defaults to `uhubctl`. |
| `uhubctl.location` | Hub as uhubctl names it. Defaults to `"2"` — the Story 1 result for this Pi. |
| `uhubctl.ports` | `null` for ganged (omits `-p`, switches the whole hub). A list or `"1,3"` targets specific ports. |
| `uhubctl.binary` | Path, if it isn't on `PATH`. |
| `uhubctl.sudo` | Prefix `sudo -n`. Leave `false` under systemd, which already runs as root. `-n` means a password prompt fails immediately instead of hanging until the timeout. |
| `uhubctl.timeout_seconds` | Per-invocation timeout. |
| `dryrun.initial_state` | Starting state for development: `true`, `false`, or `null` for unknown. |

Everything has a default, so `create_backend({})` produces the right backend for this Pi.

Adding hardware — the GPIO + relay fallback from RESEARCH.md §1 option B, say — means a new
`PowerBackend` subclass and one entry in `_BUILDERS` in `factory.py`. Nothing above the
backend changes.

### `DryRunBackend`

Logs instead of switching and remembers what it was told, so the scheduler and GUI run on a
laptop with no hub. It reports state back faithfully, which means a reconciliation loop
driving it behaves exactly as it would against real hardware.

## Errors

Every failure is a `PowerBackendError` subclass, logged at the point of failure with the
exact argv and the hub's own output:

| Error | Cause |
|---|---|
| `BackendUnavailableError` | `uhubctl` missing, hub absent or unplugged, command timed out. |
| `PermissionDeniedError` | Running without raw USB access. |
| `SwitchFailedError` | Command ran and was understood, but failed. |
| `BackendConfigError` | Settings unusable — bad port number, non-positive timeout. |
| `UnknownBackendError` | Config named a backend we don't implement. Subclass of `BackendConfigError`. |

The daemon catches the one base type, logs, and retries next tick:

```python
try:
    backend.set_power(desired)
except PowerBackendError:
    log.exception("power switch failed; will retry next tick")
```

A backend must never raise anything else out of `set_power` / `get_power`. An uncaught
error stops the reconciliation loop, and a stopped loop means a dark room all night.

`uhubctl` reports trouble in prose rather than exit codes, so classification matches on its
output text. An unrecognised failure falls through to `SwitchFailedError` with the full
output attached rather than being guessed at.

## Privileges

`uhubctl` needs raw USB access — root, in practice.

**How the service gets it (the deployed answer):** the scheduler runs as root under systemd.
Root is the unit's default user, so Story 7's unit file needs nothing special:

```ini
[Service]
ExecStart=/usr/bin/python3 -m pilight.daemon
# User is root by default; uhubctl needs it.
Restart=always
```

Set `uhubctl.sudo` to `false` for this — the process is already root, and a `sudo` hop from
a non-interactive service is a failure mode, not a safety measure. RESEARCH.md §1 endorses
starting here: "Start with root, tighten later if it matters."

**The GUI never needs any of this.** It writes a JSON file and nothing else, and runs as the
desktop user.

### Tightening it later

To run the daemon as an unprivileged user instead, grant that user write access to the hub's
device node with a udev rule — `/etc/udev/rules.d/52-pilight-usb.rules`:

```
SUBSYSTEM=="usb", DRIVER=="usb", ATTR{idVendor}=="1d6b", MODE="0664", GROUP="pilight"
```

Then `sudo udevadm control --reload && sudo udevadm trigger`, add the service user to the
`pilight` group, and drop `User=pilight` into the unit. Two caveats worth knowing before
taking this on: `1d6b` is the Linux Foundation root-hub vendor ID, so the rule grants access
to *every* root hub on the machine, not just location 2; and the rule has to survive kernel
and firmware updates that renumber devices. On a single-purpose Pi where the only untrusted
input is the sunset table, root under systemd is the proportionate answer.

## Checking it by hand

```bash
sudo python3 -m pilight.power status
sudo python3 -m pilight.power off
sudo python3 -m pilight.power on
python3 -m pilight.power on --backend dryrun   # no hardware touched
```

Exits non-zero with a one-line reason on failure. `-v` adds the raw `uhubctl` output.

## Tests

```bash
python3 -m pytest
```

The unit tests inject a fake command runner, so they need no hub, no root, and no `uhubctl`.
`tests/test_uhubctl_subprocess.py` covers the real process plumbing — argv, exit codes,
stream capture, missing binary, timeout — against a shell script standing in for `uhubctl`.
