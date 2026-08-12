"""Atomic text file writes: temp file + rename, so a reader never sees a
partially written file. Shared by the location cache (Story 4) and the main
config file (Story 5)."""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    # rw-rw-r--, explicitly, regardless of umask: files under /var/lib/pilight
    # are written by the root daemon and the unprivileged GUI (Story 9) and
    # need to be writable by both. The setgid state directory (Story 7)
    # gets group ownership right; this is what makes the group bit usable.
    tmp_path.chmod(0o664)
    os.replace(tmp_path, path)
