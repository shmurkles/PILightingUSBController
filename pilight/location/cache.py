"""Disk cache for a resolved location.

A location, once resolved, must not trigger a second network request just
because the process restarted -- this is Story 4's "cached to disk
permanently" criterion. Writes are atomic (temp file + rename) so a crash
mid-write can't leave a half-written cache behind, matching the durability
Story 5 will require of the full config file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .model import ResolvedLocation


def load_cached_location(path: Path) -> ResolvedLocation | None:
    """The cached location, or ``None`` if there isn't one yet or it's unreadable.

    A missing or corrupt cache is not an error here: it just means
    resolve_location() should move on to the next mechanism (IP geolocation,
    then the offline picker). Corruption is not expected to self-heal by
    retrying, so this doesn't raise.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return ResolvedLocation.from_dict(json.loads(text))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_cached_location(path: Path, location: ResolvedLocation) -> None:
    """Write the cache atomically: write to a temp file, then rename over the target.

    The rename is atomic on POSIX (same filesystem), so a reader never sees a
    partially written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(location.to_dict(), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)
