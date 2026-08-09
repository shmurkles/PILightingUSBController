"""Build a power backend from configuration.

Swapping hardware — say, dropping to the GPIO + relay fallback from
RESEARCH.md §1 option B — is a config edit and a new entry in ``_BUILDERS``,
never a change to the scheduler.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from .base import BackendConfigError, PowerBackend, UnknownBackendError
from .dryrun import DryRunBackend
from .uhubctl import UhubctlBackend

log = logging.getLogger(__name__)

#: Hub location found by the Story 1 spike on this Pi.
DEFAULT_UHUBCTL_LOCATION = "2"
DEFAULT_BACKEND = "uhubctl"


def create_backend(config: Mapping[str, Any] | None = None) -> PowerBackend:
    """Construct the backend named by ``config["backend"]``.

    Args:
        config: the whole config mapping, or just its backend-relevant subset.
            Missing keys fall back to this device's documented defaults.

    Raises:
        UnknownBackendError: the name is not one we implement.
        BackendConfigError: the name is right but its settings are not usable.
    """
    config = config or {}
    name = str(config.get("backend", DEFAULT_BACKEND)).strip().lower()

    builder = _BUILDERS.get(name)
    if builder is None:
        known = ", ".join(sorted(_BUILDERS))
        raise UnknownBackendError(f"unknown backend {name!r}; expected one of: {known}")

    settings = config.get(name) or {}
    if not isinstance(settings, Mapping):
        raise BackendConfigError(
            f"settings for backend {name!r} must be an object, got {type(settings).__name__}"
        )

    backend = builder(settings)
    log.info("power backend: %s", backend.describe())
    return backend


def available_backends() -> list[str]:
    return sorted(_BUILDERS)


def _build_uhubctl(settings: Mapping[str, Any]) -> PowerBackend:
    location = str(settings.get("location") or DEFAULT_UHUBCTL_LOCATION)
    return UhubctlBackend(
        location=location,
        ports=_coerce_ports(settings.get("ports")),
        binary=str(settings.get("binary") or "uhubctl"),
        sudo=bool(settings.get("sudo", False)),
        timeout_seconds=_coerce_timeout(settings.get("timeout_seconds", 10.0)),
    )


def _build_dryrun(settings: Mapping[str, Any]) -> PowerBackend:
    initial = settings.get("initial_state", False)
    if initial is not None:
        initial = bool(initial)
    return DryRunBackend(initial_state=initial)


_BUILDERS: dict[str, Callable[[Mapping[str, Any]], PowerBackend]] = {
    "uhubctl": _build_uhubctl,
    "dryrun": _build_dryrun,
}


def _coerce_ports(value: Any) -> list[int] | None:
    """Accept ``null``, a list, or a ``"1,2"`` string. Empty means ganged."""
    if value is None:
        return None
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise BackendConfigError(
            f"uhubctl 'ports' must be null, a list, or a comma-separated string, "
            f"got {type(value).__name__}"
        )

    ports: list[int] = []
    for part in parts:
        try:
            port = int(part)
        except (TypeError, ValueError) as exc:
            raise BackendConfigError(f"uhubctl port {part!r} is not a number") from exc
        if port < 1:
            raise BackendConfigError(f"uhubctl port {port} must be 1 or greater")
        ports.append(port)

    return ports or None


def _coerce_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise BackendConfigError(f"timeout_seconds {value!r} is not a number") from exc
    if timeout <= 0:
        raise BackendConfigError(f"timeout_seconds must be positive, got {timeout}")
    return timeout
