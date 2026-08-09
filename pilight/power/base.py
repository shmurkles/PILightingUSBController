"""Power backend interface and error types.

The scheduler never learns which hardware trick is underneath. It calls
``set_power`` / ``get_power`` and handles :class:`PowerBackendError`; whether that
means switching a USB hub, driving a relay off a GPIO pin, or writing to a log
file is the backend's business.
"""

from __future__ import annotations

import abc


class PowerBackendError(Exception):
    """Base class for every failure a backend can report.

    The daemon catches this one type, logs it, and retries on the next tick. A
    backend must never raise anything else out of ``set_power`` / ``get_power``:
    an uncaught error stops the reconciliation loop, and a stopped loop means a
    dark room all night.
    """


class BackendUnavailableError(PowerBackendError):
    """The backend cannot be reached at all.

    ``uhubctl`` is not installed, the hub is unplugged, or the configured
    location does not exist. Usually persistent — worth logging prominently
    rather than retrying quietly forever.
    """


class PermissionDeniedError(PowerBackendError):
    """The backend exists but this process is not allowed to drive it.

    ``uhubctl`` needs raw USB access. See docs/power-backend.md for how the
    service acquires it.
    """


class SwitchFailedError(PowerBackendError):
    """The command ran and was understood, but the port did not switch."""


class BackendConfigError(PowerBackendError):
    """The config does not describe a usable backend."""


class UnknownBackendError(BackendConfigError):
    """Config named a backend that does not exist."""


class PowerBackend(abc.ABC):
    """Turn the light on or off, and report whether it is on."""

    @abc.abstractmethod
    def set_power(self, on: bool) -> None:
        """Switch the light on (``True``) or off (``False``).

        Idempotent: calling it twice with the same value is harmless and is the
        normal case, since the reconciliation loop re-asserts state rather than
        tracking transitions.

        Raises:
            PowerBackendError: if the switch could not be performed.
        """

    @abc.abstractmethod
    def get_power(self) -> bool | None:
        """Report whether the light is currently powered.

        Returns ``None`` when the backend genuinely cannot tell — a hub whose
        ports disagree, or output it could not parse. ``None`` means "unknown",
        never "off"; a caller that treats it as off will switch the light at the
        wrong moment.

        Raises:
            PowerBackendError: if the state could not be queried at all. This is
                distinct from returning ``None``: the error means the question
                could not be asked, ``None`` means it was asked and the answer
                was ambiguous.
        """

    def describe(self) -> str:
        """One line naming this backend and its target, for startup logs."""
        return type(self).__name__
