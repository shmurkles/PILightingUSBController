"""Tests for config-driven backend selection.

Changing hardware must be a config edit, never a code edit — so these cases are
all about what a config mapping produces.
"""

from __future__ import annotations

import pytest

from pilight.power import (
    BackendConfigError,
    DryRunBackend,
    UhubctlBackend,
    UnknownBackendError,
    available_backends,
    create_backend,
)


def test_defaults_to_this_pi_spike_result():
    """Empty config gives the Story 1 answer: uhubctl, hub 2, ganged."""
    b = create_backend({})
    assert isinstance(b, UhubctlBackend)
    assert b.location == "2"
    assert b.ports is None


def test_none_config_behaves_like_empty():
    assert isinstance(create_backend(None), UhubctlBackend)


def test_selects_dryrun_by_name():
    assert isinstance(create_backend({"backend": "dryrun"}), DryRunBackend)


def test_backend_name_is_case_and_space_insensitive():
    assert isinstance(create_backend({"backend": " DryRun "}), DryRunBackend)


def test_reads_uhubctl_settings():
    b = create_backend(
        {
            "backend": "uhubctl",
            "uhubctl": {
                "location": "1-1",
                "ports": [2, 4],
                "binary": "/usr/sbin/uhubctl",
                "sudo": True,
                "timeout_seconds": 3,
            },
        }
    )
    assert (b.location, b.ports, b.binary, b.sudo) == ("1-1", [2, 4], "/usr/sbin/uhubctl", True)
    assert b.timeout_seconds == 3.0


def test_ports_accept_a_comma_string():
    b = create_backend({"uhubctl": {"ports": "1, 2"}})
    assert b.ports == [1, 2]


@pytest.mark.parametrize("value", [None, [], ""])
def test_empty_ports_mean_ganged(value):
    assert create_backend({"uhubctl": {"ports": value}}).ports is None


def test_dryrun_initial_state_is_configurable():
    assert create_backend({"backend": "dryrun", "dryrun": {"initial_state": True}}).get_power()


def test_unknown_backend_names_the_alternatives():
    with pytest.raises(UnknownBackendError, match="uhubctl"):
        create_backend({"backend": "smartplug"})


def test_settings_must_be_an_object():
    with pytest.raises(BackendConfigError, match="must be an object"):
        create_backend({"backend": "uhubctl", "uhubctl": ["location", "2"]})


@pytest.mark.parametrize(
    "ports",
    ["one", [0], [-1], ["two"], 7.5],
    ids=["word", "zero", "negative", "word-in-list", "not-a-list"],
)
def test_bad_ports_are_rejected_clearly(ports):
    with pytest.raises(BackendConfigError):
        create_backend({"uhubctl": {"ports": ports}})


@pytest.mark.parametrize("timeout", ["soon", 0, -1])
def test_bad_timeouts_are_rejected(timeout):
    with pytest.raises(BackendConfigError, match="timeout_seconds"):
        create_backend({"uhubctl": {"timeout_seconds": timeout}})


def test_config_errors_are_catchable_as_power_backend_errors():
    """The daemon catches one type; config problems must not slip past it."""
    from pilight.power import PowerBackendError

    with pytest.raises(PowerBackendError):
        create_backend({"backend": "nope"})


def test_available_backends_lists_what_is_implemented():
    assert available_backends() == ["dryrun", "uhubctl"]
