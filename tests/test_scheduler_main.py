"""Tests for the `python -m pilight.scheduler` CLI wiring."""

from __future__ import annotations

from pathlib import Path

import pilight.scheduler.__main__ as cli


class _FakeDaemon:
    instances: list["_FakeDaemon"] = []

    def __init__(self, config_path):
        self.config_path = config_path
        self.ran = False
        _FakeDaemon.instances.append(self)

    def run(self):
        self.ran = True


def _reset(monkeypatch):
    _FakeDaemon.instances = []
    monkeypatch.setattr(cli, "SchedulerDaemon", _FakeDaemon)


def test_positional_arg_is_used_as_config_path(monkeypatch):
    _reset(monkeypatch)
    cli.main(["/tmp/custom-config.json"])
    assert _FakeDaemon.instances[0].config_path == Path("/tmp/custom-config.json")
    assert _FakeDaemon.instances[0].ran is True


def test_env_var_is_used_when_no_positional_arg(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("PILIGHT_CONFIG", "/tmp/env-config.json")
    cli.main([])
    assert _FakeDaemon.instances[0].config_path == Path("/tmp/env-config.json")


def test_falls_back_to_the_documented_default_path(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.delenv("PILIGHT_CONFIG", raising=False)
    cli.main([])
    assert _FakeDaemon.instances[0].config_path == cli.DEFAULT_CONFIG_PATH
