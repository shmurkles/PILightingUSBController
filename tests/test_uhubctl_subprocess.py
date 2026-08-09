"""Exercise the real subprocess runner against a stub uhubctl.

Everything else injects a fake runner, which leaves the actual process plumbing
— argv handling, exit codes, stream capture, a missing binary — unverified.
These tests drive it for real, with a shell script standing in for uhubctl so no
hub is needed.
"""

from __future__ import annotations

import os
import stat

import pytest

from pilight.power import BackendUnavailableError, SwitchFailedError, UhubctlBackend

STUB = """#!/bin/sh
# Echoes a uhubctl-shaped status. State is remembered in a file so a
# set-then-read sequence behaves like a real hub.
STATE_FILE="{state_file}"
[ -f "$STATE_FILE" ] || echo power > "$STATE_FILE"

for arg in "$@"; do
    case "$prev" in
    -a) [ "$arg" = "on" ] && echo power > "$STATE_FILE" || echo off > "$STATE_FILE" ;;
    esac
    prev="$arg"
done

STATE=$(cat "$STATE_FILE")
echo "Current status for hub 2 [1d6b:0002, USB 2.00, 2 ports, ganged]"
if [ "$STATE" = "power" ]; then
    echo "  Port 1: 0100 power"
    echo "  Port 2: 0100 power"
else
    echo "  Port 1: 0000 off"
    echo "  Port 2: 0000 off"
fi
exit {exit_code}
"""


def make_stub(tmp_path, exit_code: int = 0) -> str:
    path = tmp_path / "uhubctl"
    path.write_text(
        STUB.format(state_file=tmp_path / "state", exit_code=exit_code),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return os.fspath(path)


def test_switch_and_read_back_through_a_real_process(tmp_path):
    b = UhubctlBackend(location="2", binary=make_stub(tmp_path))

    b.set_power(False)
    assert b.get_power() is False

    b.set_power(True)
    assert b.get_power() is True


def test_repeating_a_switch_through_a_real_process_is_harmless(tmp_path):
    b = UhubctlBackend(location="2", binary=make_stub(tmp_path))
    b.set_power(True)
    b.set_power(True)
    assert b.get_power() is True


def test_real_nonzero_exit_becomes_a_typed_error(tmp_path):
    b = UhubctlBackend(location="2", binary=make_stub(tmp_path, exit_code=3))
    with pytest.raises(SwitchFailedError):
        b.set_power(True)


def test_genuinely_missing_binary(tmp_path):
    b = UhubctlBackend(location="2", binary=os.fspath(tmp_path / "definitely-not-here"))
    with pytest.raises(BackendUnavailableError, match="not found"):
        b.set_power(True)


def test_timeout_against_a_hanging_binary(tmp_path):
    hanging = tmp_path / "hanging-uhubctl"
    hanging.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    hanging.chmod(hanging.stat().st_mode | stat.S_IEXEC)

    b = UhubctlBackend(location="2", binary=os.fspath(hanging), timeout_seconds=0.5)
    with pytest.raises(BackendUnavailableError, match="unresponsive"):
        b.set_power(True)
