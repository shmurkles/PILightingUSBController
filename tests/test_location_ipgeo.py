"""Tests for IP geolocation, entirely against a fake urlopen -- no real network call."""

from __future__ import annotations

import json
import urllib.error

import pytest

from pilight.location.errors import NoNetworkError
from pilight.location.ipgeo import IPLocation, geolocate_by_ip


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_parses_a_successful_response(monkeypatch):
    payload = {
        "latitude": 45.5152,
        "longitude": -122.6784,
        "city": "Portland",
        "country_name": "United States",
        "timezone": "America/Los_Angeles",
    }
    monkeypatch.setattr(
        "pilight.location.ipgeo.urllib.request.urlopen",
        lambda *a, **k: _FakeResponse(payload),
    )
    result = geolocate_by_ip()
    assert result == IPLocation(
        45.5152, -122.6784, "Portland", "United States", "America/Los_Angeles"
    )


def test_network_error_is_wrapped(monkeypatch):
    def raise_it(*a, **k):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("pilight.location.ipgeo.urllib.request.urlopen", raise_it)
    with pytest.raises(NoNetworkError):
        geolocate_by_ip()


def test_non_200_status_is_a_network_error(monkeypatch):
    monkeypatch.setattr(
        "pilight.location.ipgeo.urllib.request.urlopen",
        lambda *a, **k: _FakeResponse({}, status=503),
    )
    with pytest.raises(NoNetworkError):
        geolocate_by_ip()


def test_provider_error_payload_is_a_network_error(monkeypatch):
    monkeypatch.setattr(
        "pilight.location.ipgeo.urllib.request.urlopen",
        lambda *a, **k: _FakeResponse({"error": True, "reason": "RateLimited"}),
    )
    with pytest.raises(NoNetworkError):
        geolocate_by_ip()


def test_missing_fields_is_a_network_error(monkeypatch):
    monkeypatch.setattr(
        "pilight.location.ipgeo.urllib.request.urlopen",
        lambda *a, **k: _FakeResponse({"latitude": 1.0}),
    )
    with pytest.raises(NoNetworkError):
        geolocate_by_ip()


def test_unparseable_json_is_a_network_error(monkeypatch):
    class BadResponse(_FakeResponse):
        def read(self):
            return b"not json"

    monkeypatch.setattr(
        "pilight.location.ipgeo.urllib.request.urlopen",
        lambda *a, **k: BadResponse({}),
    )
    with pytest.raises(NoNetworkError):
        geolocate_by_ip()
