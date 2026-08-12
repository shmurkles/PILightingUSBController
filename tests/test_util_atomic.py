"""Tests for the shared atomic-write helper."""

from __future__ import annotations

import stat

from pilight.util.atomic import atomic_write_text


def test_writes_the_given_text(tmp_path):
    path = tmp_path / "file.txt"
    atomic_write_text(path, "hello")
    assert path.read_text(encoding="utf-8") == "hello"


def test_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "file.txt"
    atomic_write_text(path, "hello")
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_creates_parent_directories(tmp_path):
    path = tmp_path / "a" / "b" / "file.txt"
    atomic_write_text(path, "hello")
    assert path.exists()


def test_file_is_group_writable_regardless_of_umask(tmp_path):
    path = tmp_path / "file.txt"
    atomic_write_text(path, "hello")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & stat.S_IWGRP
    assert mode & stat.S_IWUSR


def test_overwriting_an_existing_file_still_ends_up_group_writable(tmp_path):
    path = tmp_path / "file.txt"
    atomic_write_text(path, "first")
    path.chmod(0o600)  # simulate a file that started out not group-writable
    atomic_write_text(path, "second")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & stat.S_IWGRP
    assert path.read_text() == "second"
