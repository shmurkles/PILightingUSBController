"""Tests for the uhubctl backend.

The command runner is injected, so every case here is hermetic — no hub, no
root, no uhubctl binary required. The sample outputs are real uhubctl formats.
"""

from __future__ import annotations

import logging
import subprocess

import pytest

from pilight.power import (
    BackendUnavailableError,
    PermissionDeniedError,
    SwitchFailedError,
    UhubctlBackend,
)
from pilight.power.uhubctl import CommandResult

HUB_HEADER = (
    "Current status for hub 2 [1d6b:0002 Linux 6.6.51+rpt-rpi-v8 xhci-hcd "
    "xHCI Host Controller 0000:01:00.0, USB 2.00, 4 ports, ganged]"
)

POWERED = f"""{HUB_HEADER}
  Port 1: 0503 power highspeed enable connect [1a86:7523 USB Serial]
  Port 2: 0100 power
  Port 3: 0100 power
  Port 4: 0100 power
"""

UNPOWERED = f"""{HUB_HEADER}
  Port 1: 0000 off
  Port 2: 0000 off
  Port 3: 0000 off
  Port 4: 0000 off
"""

# uhubctl echoes the state before and after a switch.
SWITCH_OFF_TRANSCRIPT = f"""{HUB_HEADER}
  Port 1: 0503 power highspeed enable connect
Sent power off request
New status for hub 2 [1d6b:0002 Linux 6.6.51+rpt-rpi-v8 xhci-hcd, USB 2.00, 4 ports, ganged]
  Port 1: 0000 off
"""


class FakeRunner:
    """Records argv and replays canned results."""

    def __init__(self, *results: CommandResult | Exception) -> None:
        self._results = list(results) or [CommandResult(0, POWERED, "")]
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout):  # noqa: ANN001, ANN204 - matches CommandRunner
        self.calls.append(list(argv))
        result = self._results[min(len(self.calls) - 1, len(self._results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result

    @property
    def last(self) -> list[str]:
        return self.calls[-1]


def backend(*results, **kwargs) -> tuple[UhubctlBackend, FakeRunner]:
    runner = FakeRunner(*results)
    kwargs.setdefault("location", "2")
    return UhubctlBackend(runner=runner, **kwargs), runner


# -- command construction ----------------------------------------------------


def test_ganged_switch_omits_port_flag():
    """No -p is the whole point of the Story 1 ganged decision."""
    b, runner = backend(CommandResult(0, SWITCH_OFF_TRANSCRIPT, ""))
    b.set_power(False)
    assert runner.last == ["uhubctl", "-l", "2", "-a", "off"]


def test_set_power_on_uses_on_action():
    b, runner = backend(CommandResult(0, POWERED, ""))
    b.set_power(True)
    assert runner.last == ["uhubctl", "-l", "2", "-a", "on"]


def test_explicit_ports_are_passed_through():
    b, runner = backend(CommandResult(0, POWERED, ""), ports=[1, 3])
    b.set_power(True)
    assert runner.last == ["uhubctl", "-l", "2", "-p", "1,3", "-a", "on"]


def test_sudo_is_non_interactive():
    """-n so a password prompt fails fast instead of hanging until the timeout."""
    b, runner = backend(CommandResult(0, POWERED, ""), sudo=True)
    b.set_power(True)
    assert runner.last[:2] == ["sudo", "-n"]


def test_custom_binary_path():
    b, runner = backend(CommandResult(0, POWERED, ""), binary="/usr/local/bin/uhubctl")
    b.set_power(True)
    assert runner.last[0] == "/usr/local/bin/uhubctl"


def test_setting_the_same_state_twice_is_harmless():
    b, runner = backend(CommandResult(0, POWERED, ""))
    b.set_power(True)
    b.set_power(True)
    assert len(runner.calls) == 2
    assert all(call[-2:] == ["-a", "on"] for call in runner.calls)


def test_set_power_does_not_query_state_first():
    """The reconcile loop asserts state every tick; a read-back here is wasted I/O."""
    b, runner = backend(CommandResult(0, POWERED, ""))
    b.set_power(True)
    assert len(runner.calls) == 1


# -- status parsing ----------------------------------------------------------


def test_get_power_reads_powered_hub():
    b, _ = backend(CommandResult(0, POWERED, ""))
    assert b.get_power() is True


def test_get_power_reads_unpowered_hub():
    b, _ = backend(CommandResult(0, UNPOWERED, ""))
    assert b.get_power() is False


def test_get_power_queries_without_an_action_flag():
    b, runner = backend(CommandResult(0, POWERED, ""))
    b.get_power()
    assert "-a" not in runner.last


def test_later_status_blocks_win():
    """uhubctl prints old status then new; the new one is the answer."""
    b, _ = backend(CommandResult(0, SWITCH_OFF_TRANSCRIPT, ""))
    assert b.get_power() is False


def test_mixed_port_states_are_unknown_not_off(caplog):
    mixed = f"{HUB_HEADER}\n  Port 1: 0100 power\n  Port 2: 0000 off\n"
    b, _ = backend(CommandResult(0, mixed, ""))
    with caplog.at_level(logging.WARNING):
        assert b.get_power() is None
    assert "mixed" in caplog.text


def test_unparseable_output_is_unknown(caplog):
    b, _ = backend(CommandResult(0, "something entirely unexpected", ""))
    with caplog.at_level(logging.WARNING):
        assert b.get_power() is None
    assert "unknown" in caplog.text.lower()


# -- failure classification --------------------------------------------------


def test_missing_binary_is_backend_unavailable():
    b, _ = backend(FileNotFoundError("uhubctl"))
    with pytest.raises(BackendUnavailableError, match="apt install"):
        b.set_power(True)


def test_permission_trouble_is_permission_denied():
    stderr = "Permission denied opening device 2\nThere were permission problems"
    b, _ = backend(CommandResult(1, "", stderr))
    with pytest.raises(PermissionDeniedError, match="raw USB"):
        b.set_power(True)


def test_absent_hub_is_backend_unavailable():
    b, _ = backend(CommandResult(1, "No compatible devices detected", ""))
    with pytest.raises(BackendUnavailableError, match="location 2"):
        b.set_power(True)


def test_unrecognised_failure_is_switch_failed():
    b, _ = backend(CommandResult(1, "", "something went sideways"))
    with pytest.raises(SwitchFailedError, match="sideways"):
        b.set_power(True)


def test_timeout_is_backend_unavailable():
    b, _ = backend(subprocess.TimeoutExpired(cmd="uhubctl", timeout=10.0))
    with pytest.raises(BackendUnavailableError, match="unresponsive"):
        b.set_power(True)


def test_get_power_also_raises_typed_errors():
    """Errors are for 'could not ask'; None is for 'asked, answer ambiguous'."""
    b, _ = backend(FileNotFoundError("uhubctl"))
    with pytest.raises(BackendUnavailableError):
        b.get_power()


def test_failures_are_logged_with_context(caplog):
    b, _ = backend(CommandResult(1, "", "Permission denied"))
    with caplog.at_level(logging.ERROR), pytest.raises(PermissionDeniedError):
        b.set_power(True)
    assert "PermissionDeniedError" in caplog.text
    assert "uhubctl -l 2 -a on" in caplog.text


def test_error_message_names_the_command():
    b, _ = backend(CommandResult(1, "", "nope"))
    with pytest.raises(SwitchFailedError, match=r"uhubctl -l 2 -a off"):
        b.set_power(False)


# -- description -------------------------------------------------------------


def test_describe_reports_ganged():
    b, _ = backend()
    assert b.describe() == "uhubctl hub 2 (ganged, all ports)"


def test_describe_reports_specific_ports():
    b, _ = backend(ports=[2])
    assert b.describe() == "uhubctl hub 2 (ports 2)"
