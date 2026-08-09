"""Tests for the development backend."""

from __future__ import annotations

import logging

from pilight.power import DryRunBackend


def test_reports_back_what_it_was_told():
    b = DryRunBackend()
    b.set_power(True)
    assert b.get_power() is True
    b.set_power(False)
    assert b.get_power() is False


def test_starts_off_by_default():
    assert DryRunBackend().get_power() is False


def test_initial_state_can_be_unknown():
    assert DryRunBackend(initial_state=None).get_power() is None


def test_records_every_call_for_assertions():
    b = DryRunBackend()
    b.set_power(True)
    b.set_power(False)
    b.set_power(True)
    assert b.calls == [True, False, True]


def test_repeating_a_state_is_harmless():
    b = DryRunBackend()
    b.set_power(True)
    b.set_power(True)
    assert b.get_power() is True
    assert b.calls == [True, True]


def test_transitions_log_at_info_and_repeats_do_not(caplog):
    """Story 12 wants routine no-change ticks quiet at the default level."""
    b = DryRunBackend()
    with caplog.at_level(logging.INFO):
        b.set_power(True)
        assert "switching light on" in caplog.text
        caplog.clear()
        b.set_power(True)
        assert caplog.text == ""


def test_describe_is_unmistakable():
    assert "no hardware" in DryRunBackend().describe()
