# Story 7 — systemd service

**Status:** deployed and verified on the real device.

## Decision

`deploy/pilight-scheduler.service` runs `python -m pilight.scheduler` from a dedicated venv
at `/opt/pilight/venv`, reading config from `/var/lib/pilight/config.json` (`PILIGHT_CONFIG`).
`Restart=always` covers both a crash and the reboot case; `Type=simple` is correct since the
process never forks or signals readiness -- it just runs the reconciliation loop forever.

Runs as `root`: `uhubctl` needs raw USB access (RESEARCH.md §1), so this is exactly the
privilege the backend requires, not more. The udev-rule alternative is documented in
[docs/power-backend.md](./power-backend.md) as the tightening option, not applied by default.

Logs go to stderr via `logging.basicConfig`, which systemd captures into the journal for any
service automatically -- no journald-specific code needed. `journalctl -u pilight-scheduler`
shows every reconciliation decision and transition Story 12 will structure further.

## Why `/var/lib/pilight`

Story 5 and Story 6 both take a `path` argument rather than hardcoding one, deliberately
leaving "where does this actually live" to whoever deploys it. `/var/lib/<service>/` is the
conventional location for a system daemon's mutable state on Linux, which is exactly what
`config.json` and the location cache are. The directory is created group-writable by a
dedicated `pilight` group (with the desktop user added to it) rather than owned solely by
root, so Story 9's GUI -- running unprivileged as the desktop user -- can write `config.json`
without needing root itself. The daemon (root) can write there regardless of the group,
since root bypasses permission checks.

## No GUI yet to seed a location

Story 6's daemon reads `config.location` but never resolves it -- that's deliberately the
GUI's job (Story 9). Since Story 8/9 don't exist yet, `python -m pilight.location resolve
<config_path>` (added alongside this story) is the documented stand-in: it runs Story 4's
`resolve_location()` once, by hand, and writes the result into the config file Story 7's
service reads. This isn't Story 8/9's scope creeping in -- it's a thin CLI wrapper around
already-built Story 4/5 code, useful on its own for scripting and debugging regardless of
whether the GUI ever runs on a given device (e.g. a headless install).

## Install

```bash
# One-time: a dedicated venv, separate from any personal dev checkout.
sudo mkdir -p /opt/pilight
sudo git clone https://github.com/shmurkles/PILightingUSBController.git /opt/pilight/src
sudo python3 -m venv /opt/pilight/venv
sudo /opt/pilight/venv/bin/pip install /opt/pilight/src

# State directory, shared between the root daemon and the (future) unprivileged GUI.
sudo groupadd -f pilight
sudo usermod -aG pilight "$USER"
sudo mkdir -p /var/lib/pilight
sudo chown root:pilight /var/lib/pilight
sudo chmod 2775 /var/lib/pilight

# Seed a location once, before the service can do anything useful.
sudo /opt/pilight/venv/bin/python -m pilight.location resolve /var/lib/pilight/config.json

# Install and start the service.
sudo cp /opt/pilight/src/deploy/pilight-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pilight-scheduler
```

## Acceptance criteria

- [x] Unit file starts at boot with no login (`WantedBy=multi-user.target`, no `User=` login
      session involved), `Restart=always`.
- [x] Logs go to the journal -- `journalctl -u pilight-scheduler` shows decisions and
      transitions (stderr is captured automatically; no extra code needed).
- [x] Runs with exactly the privileges the backend requires (root, for raw USB access) and
      no more.
- [x] Verified: full reboot -> light is in the correct state within one loop interval.
      Deployed 2026-08-10 (location resolved to Edmonton, Canada via IP geolocation,
      confirmed against the device's own `/etc/timezone`, also `America/Edmonton`). After
      `sudo reboot`, the service auto-started, loaded config, and switched the light off on
      its first tick (now was past the 23:30 default off-time) -- confirmed physically via
      `uhubctl -l 2`, all four ports reporting off.
- [x] `enable` / `disable` / `status` documented -- see the README's Scheduler daemon
      section.

## Deployment log

```
$ sudo systemctl enable --now pilight-scheduler
$ sudo journalctl -u pilight-scheduler -b --no-pager
Aug 10 23:31:35 shmurkles systemd[1]: Started pilight-scheduler.service
Aug 10 23:31:36 shmurkles python[774]: INFO __main__: starting scheduler daemon, config=/var/lib/pilight/config.json
Aug 10 23:31:36 shmurkles python[774]: INFO pilight.scheduler.daemon: config (re)loaded from /var/lib/pilight/config.json
Aug 10 23:31:36 shmurkles python[774]: INFO pilight.power.factory: power backend: uhubctl hub 2 (ganged, all ports)
Aug 10 23:31:39 shmurkles python[774]: INFO pilight.power.uhubctl: uhubctl set power off for hub 2 (ganged, all ports)
Aug 10 23:31:39 shmurkles python[774]: INFO pilight.scheduler.daemon: switched light off (on=2026-08-10T21:11:57-06:00 off=2026-08-10T23:30:00-06:00)
```
