"""Power backend driving ``uhubctl``.

Story 1 established the mechanism for this Pi: hub location ``2``, switched
ganged (all downstream ports at once, no ``-p``), which is fine because the
light is the only device on it. See docs/story-1-usb-power-spike.md.
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from collections.abc import Sequence
from typing import NamedTuple, Protocol

from .base import (
    BackendUnavailableError,
    PermissionDeniedError,
    PowerBackend,
    PowerBackendError,
    SwitchFailedError,
)

log = logging.getLogger(__name__)

# "  Port 1: 0503 power highspeed enable connect"
_PORT_LINE = re.compile(r"^\s*Port\s+(\d+):\s+([0-9a-fA-F]{4})\s*(.*)$")

# uhubctl reports trouble in prose rather than in exit codes, so the text is all
# we have to classify a failure by.
_PERMISSION_HINTS = (
    "permission denied",
    "permission problem",
    "operation not permitted",
    "access denied",
    "no permission",
)
_MISSING_HINTS = (
    "no compatible devices detected",
    "no compatible smart hubs detected",
    "no such device",
    "not found",
)


class CommandResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """Both streams together — uhubctl is inconsistent about which it uses."""
        return f"{self.stdout}\n{self.stderr}"


class CommandRunner(Protocol):
    def __call__(self, argv: Sequence[str], timeout: float) -> CommandResult: ...


def run_subprocess(argv: Sequence[str], timeout: float) -> CommandResult:
    """Default runner. Raises FileNotFoundError / TimeoutExpired for the caller to map."""
    completed = subprocess.run(  # noqa: S603 - argv is built here, never shell-parsed
        list(argv),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class UhubctlBackend(PowerBackend):
    """Switch USB port power with ``uhubctl``.

    Args:
        location: hub location as uhubctl reports it (``"2"``, ``"1-1"``, ...).
        ports: ports to switch, or ``None`` for ganged — every port on the hub.
        binary: path to uhubctl.
        sudo: prefix with ``sudo -n``. Leave off when the daemon already runs as
            root, which is how it is deployed; ``-n`` is used so a sudo password
            prompt fails immediately instead of hanging until the timeout.
        timeout_seconds: per-invocation timeout.
        runner: command executor, injectable for tests.
    """

    def __init__(
        self,
        location: str,
        ports: Sequence[int] | None = None,
        *,
        binary: str = "uhubctl",
        sudo: bool = False,
        timeout_seconds: float = 10.0,
        runner: CommandRunner = run_subprocess,
    ) -> None:
        self.location = str(location)
        self.ports = list(ports) if ports else None
        self.binary = binary
        self.sudo = sudo
        self.timeout_seconds = timeout_seconds
        self._run = runner

    # -- public interface ----------------------------------------------------

    def set_power(self, on: bool) -> None:
        action = "on" if on else "off"
        result = self._uhubctl("-a", action)
        log.info(
            "uhubctl set power %s for hub %s (%s)",
            action,
            self.location,
            self._port_description(),
        )
        log.debug("uhubctl output: %s", result.output.strip())

    def get_power(self) -> bool | None:
        result = self._uhubctl()
        states = self._parse_port_states(result.stdout)

        if not states:
            log.warning(
                "uhubctl reported no port status for hub %s; state unknown. Output: %s",
                self.location,
                result.output.strip(),
            )
            return None

        powered = set(states.values())
        if len(powered) == 1:
            return powered.pop()

        # A ganged hub should never land here; a per-port hub legitimately can.
        log.warning(
            "hub %s reports mixed port power %s; state unknown",
            self.location,
            states,
        )
        return None

    def describe(self) -> str:
        return f"uhubctl hub {self.location} ({self._port_description()})"

    # -- internals -----------------------------------------------------------

    def _argv(self, *extra: str) -> list[str]:
        argv: list[str] = []
        if self.sudo:
            argv += ["sudo", "-n"]
        argv += [self.binary, "-l", self.location]
        if self.ports:
            argv += ["-p", ",".join(str(p) for p in self.ports)]
        argv += list(extra)
        return argv

    def _port_description(self) -> str:
        if self.ports:
            return "ports " + ",".join(str(p) for p in self.ports)
        return "ganged, all ports"

    def _uhubctl(self, *extra: str) -> CommandResult:
        argv = self._argv(*extra)
        printable = shlex.join(argv)

        try:
            result = self._run(argv, self.timeout_seconds)
        except FileNotFoundError as exc:
            raise self._fail(
                BackendUnavailableError(
                    f"{self.binary} not found. Install it with: sudo apt install -y uhubctl"
                )
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise self._fail(
                BackendUnavailableError(
                    f"{printable} did not finish within {self.timeout_seconds}s; "
                    "the hub may be unresponsive"
                )
            ) from exc
        except OSError as exc:
            raise self._fail(
                BackendUnavailableError(f"could not execute {printable}: {exc}")
            ) from exc

        if result.returncode != 0:
            raise self._fail(self._classify(printable, result))
        return result

    @staticmethod
    def _fail(error: PowerBackendError) -> PowerBackendError:
        """Log an error on its way out.

        Logged here rather than at the catch site because this is where the
        argv and the hub's own output are in scope. The daemon catches
        :class:`PowerBackendError`, keeps running, and retries next tick — the
        journal already has the detail it needs by then.
        """
        log.error("%s: %s", type(error).__name__, error)
        return error

    def _classify(self, printable: str, result: CommandResult) -> PowerBackendError:
        """Turn a non-zero uhubctl exit into the most specific error we can justify."""
        haystack = result.output.lower()
        detail = result.output.strip() or f"exit status {result.returncode}"

        if any(hint in haystack for hint in _PERMISSION_HINTS):
            return PermissionDeniedError(
                f"{printable} was denied access to the hub. uhubctl needs raw USB "
                f"access; see docs/power-backend.md. Output: {detail}"
            )
        if any(hint in haystack for hint in _MISSING_HINTS):
            return BackendUnavailableError(
                f"{printable} found no switchable hub at location {self.location}. "
                f"Output: {detail}"
            )
        return SwitchFailedError(f"{printable} failed: {detail}")

    @staticmethod
    def _parse_port_states(output: str) -> dict[int, bool]:
        """Map port number to powered-or-not from a uhubctl status listing.

        A port line looks like ``Port 1: 0503 power highspeed enable connect``;
        an unpowered one like ``Port 1: 0000 off``. The ``power`` flag is the
        one that matters. When uhubctl prints several status blocks — it echoes
        both the old and the new status after a switch — later blocks overwrite
        earlier ones, leaving the most recent state.
        """
        states: dict[int, bool] = {}
        for line in output.splitlines():
            match = _PORT_LINE.match(line)
            if not match:
                continue
            port = int(match.group(1))
            flags = match.group(3).split()
            states[port] = "power" in flags
        return states
