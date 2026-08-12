"""SchedulerDaemon: the stateful loop around compute_schedule().

Everything that can fail here -- a missing location, a corrupt config (config.io
already degrades that to defaults, but this layer still guards), a backend
error -- is logged and left for the next tick. A tick must never raise: an
uncaught exception here means the loop dies and the light is stuck in
whatever state it was last in, possibly all night.
"""

from __future__ import annotations

import logging
import time as time_module
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
from typing import Callable

from pilight.config import PiLightConfig, load_config, save_config
from pilight.power import PowerBackend, PowerBackendError, create_backend
from pilight.status import DaemonStatus, load_status, save_status
from pilight.sun import get_sunset

from .window import compute_schedule

log = logging.getLogger(__name__)

TICK_SECONDS = 30.0


def _default_now() -> datetime:
    return datetime.now().astimezone()


class SchedulerDaemon:
    """Owns the reconciliation loop.

    Config and the power backend are both re-created lazily, only when
    something relevant changes -- the config file's mtime for the former,
    the backend name/settings for the latter -- so a normal tick with no
    changes does no filesystem or subprocess work beyond the sunset
    calculation (which is pure arithmetic; see pilight.sun) and one backend
    state query.
    """

    def __init__(
        self,
        config_path: Path,
        *,
        status_path: Path | None = None,
        now_fn: Callable[[], datetime] = _default_now,
        get_sunset_fn: Callable[..., datetime] = get_sunset,
    ):
        self._config_path = config_path
        self._status_path = status_path or config_path.with_name("status.json")
        self._now_fn = now_fn
        self._get_sunset_fn = get_sunset_fn

        self._loaded_config: PiLightConfig | None = None
        self._loaded_mtime: float | None = None
        self._backend: PowerBackend | None = None
        self._backend_key: tuple | None = None

        # Seed continuity across a restart: an existing status file's last
        # transition is still true history, not something that happened to
        # have never occurred just because the process did.
        existing = load_status(self._status_path)
        self._last_transition_at = existing.last_transition_at if existing else None
        self._last_transition_to = existing.last_transition_to if existing else None

    def _reload_config_if_changed(self) -> tuple[PiLightConfig, bool]:
        try:
            mtime = self._config_path.stat().st_mtime
        except OSError:
            mtime = None
        reloaded = self._loaded_config is None or mtime != self._loaded_mtime
        if reloaded:
            self._loaded_config = load_config(self._config_path)
            self._loaded_mtime = mtime
            log.info("config (re)loaded from %s", self._config_path)
        return self._loaded_config, reloaded

    def _backend_for(self, config: PiLightConfig) -> PowerBackend:
        settings = config.backend_settings.get(config.backend, {})
        key = (config.backend, tuple(sorted(settings.items())))
        if self._backend is None or key != self._backend_key:
            self._backend = create_backend(config.to_dict())
            self._backend_key = key
            log.info("power backend (re)created: %s", self._backend.describe())
        return self._backend

    def tick(self) -> None:
        """Run one reconciliation step. Never raises."""
        try:
            config, reloaded = self._reload_config_if_changed()
        except Exception:
            log.exception("failed to load config from %s; skipping this tick", self._config_path)
            return

        location = config.location
        if location is None:
            log.warning("no location resolved yet; skipping this tick")
            return

        try:
            off_time_value = time.fromisoformat(config.off_time)
        except ValueError:
            log.error("config off_time=%r is not parseable; skipping this tick", config.off_time)
            return

        def sunset_for(d: date) -> datetime:
            return self._get_sunset_fn(d, lat=location.lat, lon=location.lon, tz=location.timezone)

        now = self._now_fn()
        decision = compute_schedule(now, sunset_for, config.offset_minutes, off_time_value)

        if reloaded:
            # Logged on every (re)load, not just process startup: a location
            # or offset change from the GUI is exactly the kind of thing a
            # diagnosis needs visible in the journal, not only the first line.
            log.info(
                "location: %s, %s (%.5f, %.5f) tz=%s source=%s | today's sunset=%s",
                location.city,
                location.country,
                location.lat,
                location.lon,
                location.timezone,
                location.source,
                decision.sunset.isoformat() if decision.sunset else "n/a (polar fallback)",
            )

        if not decision.window_valid:
            log.warning("invalid schedule window: %s", decision.reason)
        if decision.used_polar_fallback:
            log.warning(
                "sun does not set/rise today at this location; using fallback on-time %s",
                decision.on_time.time(),
            )

        # Manual override (Story 10): forces desired_on until the instant
        # that was, at override-set time, the schedule's own next
        # transition. Once that instant passes, clear it from config so the
        # GUI's "override active" display and this check both go back to
        # agreeing with the plain schedule -- persisted immediately rather
        # than only in memory, so the clearing survives a restart too.
        #
        # This is the one case where the daemon itself writes config.json
        # (every other write is the GUI's). A GUI edit landing in the same
        # instant could theoretically be clobbered by this write reading a
        # stale copy -- an accepted risk for a single-user device, not worth
        # a locking protocol over.
        desired_on = decision.desired_on
        override_active = False
        override = config.manual_override
        if override is not None:
            if now < override.until:
                desired_on = override.state
                override_active = True
            else:
                log.info(
                    "manual override lapsed at %s; resuming automatic control",
                    override.until.isoformat(),
                )
                config = replace(config, manual_override=None)
                self._loaded_config = config
                try:
                    save_config(self._config_path, config)
                    self._loaded_mtime = self._config_path.stat().st_mtime
                except OSError as exc:
                    log.error("could not clear lapsed manual override (%s)", exc)

        try:
            backend = self._backend_for(config)
        except PowerBackendError as exc:
            log.error("could not create power backend (%s); skipping this tick", exc)
            return

        try:
            actual = backend.get_power()
            if actual != desired_on:
                backend.set_power(desired_on)
                self._last_transition_at = now
                self._last_transition_to = desired_on
                reason = "manual override" if override_active else "scheduled"
                log.info(
                    "switched light %s: sunset=%s on=%s off=%s reason=%s",
                    "on" if desired_on else "off",
                    decision.sunset.isoformat() if decision.sunset else "n/a (polar fallback)",
                    decision.on_time.isoformat(),
                    decision.off_time.isoformat(),
                    reason,
                )
            # Reconciliation succeeded (no exception below this point), so the
            # true current state is now desired_on regardless of which
            # branch above ran.
            save_status(
                self._status_path,
                DaemonStatus(
                    actual_on=desired_on,
                    desired_on=desired_on,
                    last_transition_at=self._last_transition_at,
                    last_transition_to=self._last_transition_to,
                    updated_at=now,
                ),
            )
        except PowerBackendError as exc:
            log.error("power backend error (%s); will retry next tick", exc)

    def run(
        self,
        *,
        sleep_fn: Callable[[float], None] = time_module.sleep,
        iterations: int | None = None,
    ) -> None:
        """Loop forever, one tick every ``TICK_SECONDS``.

        Args:
            sleep_fn: injection point for tests.
            iterations: run this many ticks and return, instead of forever.
                Tests use this; real usage (Story 7's systemd unit) leaves it
                ``None``.
        """
        count = 0
        while True:
            self.tick()
            count += 1
            if iterations is not None and count >= iterations:
                return
            sleep_fn(TICK_SECONDS)
