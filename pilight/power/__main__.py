"""Manual check for the power backend.

    sudo python3 -m pilight.power status
    sudo python3 -m pilight.power on
    sudo python3 -m pilight.power off

Exists so Story 2 can be demonstrated on the Pi without the scheduler. The
daemon does not use this; it calls :func:`pilight.power.create_backend` directly.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .base import PowerBackendError
from .factory import create_backend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pilight.power", description=__doc__)
    parser.add_argument("action", choices=["on", "off", "status"])
    parser.add_argument(
        "--config",
        type=Path,
        help="JSON file with backend settings; defaults to this Pi's spike result",
    )
    parser.add_argument(
        "--backend",
        help="override the configured backend name (e.g. dryrun)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config: dict = {}
    if args.config:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"could not read {args.config}: {exc}", file=sys.stderr)
            return 2
    if args.backend:
        config["backend"] = args.backend

    try:
        backend = create_backend(config)
        if args.action == "status":
            state = backend.get_power()
            print({True: "on", False: "off", None: "unknown"}[state])
        else:
            backend.set_power(args.action == "on")
            print(f"light {args.action}")
    except PowerBackendError as exc:
        # Already logged with full context by the backend; keep this terse.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
