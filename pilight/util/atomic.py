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
    os.replace(tmp_path, path)
