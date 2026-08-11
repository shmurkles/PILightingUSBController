"""Tests for timezone priority resolution."""

from __future__ import annotations

import pytest

from pilight.location.errors import TimezoneUnavailableError
from pilight.location.timezone import read_system_timezone, resolve_timezone


def test_system_timezone_wins_when_available():
    assert resolve_timezone("IP/TZ", "City/TZ", system_timezone="System/TZ") == "System/TZ"


def test_falls_back_to_ip_timezone_when_system_unavailable():
    assert resolve_timezone("IP/TZ", "City/TZ", system_timezone=None) == "IP/TZ"


def test_falls_back_to_city_timezone_when_system_and_ip_unavailable():
    assert resolve_timezone(None, "City/TZ", system_timezone=None) == "City/TZ"


def test_raises_when_nothing_is_available():
    with pytest.raises(TimezoneUnavailableError):
        resolve_timezone(None, None, system_timezone=None)


def test_default_actually_calls_read_system_timezone(monkeypatch):
    monkeypatch.setattr("pilight.location.timezone.read_system_timezone", lambda: "Called/TZ")
    assert resolve_timezone("IP/TZ") == "Called/TZ"


def test_reads_the_real_system_timezone_on_this_device():
    # Sanity check against the actual machine running the suite (the Pi in
    # CI-on-device, or a dev box with /etc/timezone or /etc/localtime).
    assert read_system_timezone()
