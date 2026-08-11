"""CLI: python -m pilight.location resolve <config_path>

Resolves this device's location (manual override -> cache -> IP geolocation
-> offline picker) and writes it into the given pilight config file's
"location" field. Story 8/9's GUI will eventually drive this interactively
from within the app; until then, this is the documented way to seed or
refresh it by hand -- including for Story 7's initial deployment, which has
no GUI yet to do it any other way.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from pilight.config import load_config, save_config

from .citydb import CityRecord
from .resolve import resolve_location

log = logging.getLogger(__name__)


def _prompt_picker(cities: Sequence[CityRecord]) -> CityRecord:
    """Fallback used only when IP geolocation fails (no network at first run)."""
    print("No network reachable for IP geolocation. Pick your city.")
    query = input("City name (or part of it): ").strip().lower()
    matches = [c for c in cities if query in c.name.lower()][:20]
    if not matches:
        raise SystemExit(f"no city matching {query!r} found")
    for i, city in enumerate(matches):
        print(f"  {i}: {city.name}, {city.country} ({city.timezone})")
    choice = int(input("Number: ").strip())
    return matches[choice]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="python -m pilight.location")
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve", help="resolve and store this device's location")
    resolve_parser.add_argument("config_path", type=Path)
    resolve_parser.add_argument(
        "--redetect", action="store_true", help="ignore any cached location and re-detect"
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")

    if args.command == "resolve":
        cache_path = args.config_path.with_name("location_cache.json")
        location = resolve_location(cache_path, picker=_prompt_picker, force_redetect=args.redetect)
        config = load_config(args.config_path)
        save_config(args.config_path, replace(config, location=location))
        print(
            f"Resolved location: {location.city}, {location.country} "
            f"({location.lat}, {location.lon}), tz={location.timezone}, source={location.source}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
