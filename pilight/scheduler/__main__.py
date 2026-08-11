"""CLI entry point: python -m pilight.scheduler [config_path]

Runs the reconciliation loop forever. Story 7's systemd unit
(deploy/pilight-scheduler.service) is what actually starts this at boot;
running it by hand is for development/debugging.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .daemon import SchedulerDaemon

DEFAULT_CONFIG_PATH = Path("/var/lib/pilight/config.json")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        config_path = Path(argv[0])
    else:
        config_path = Path(os.environ.get("PILIGHT_CONFIG", DEFAULT_CONFIG_PATH))

    logging.basicConfig(
        level=os.environ.get("PILIGHT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger(__name__).info("starting scheduler daemon, config=%s", config_path)

    SchedulerDaemon(config_path).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
