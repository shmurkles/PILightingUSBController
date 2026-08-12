"""CLI entry point: python -m pilight.gui [config_path]

Opens the configuration window. Needs a real display -- run this from the
Pi's desktop (directly, or over Pi Connect), not a plain SSH session.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pilight.config import DEFAULT_CONFIG_PATH

from .app import PiLightGUI


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        config_path = Path(argv[0])
    else:
        config_path = Path(os.environ.get("PILIGHT_CONFIG", DEFAULT_CONFIG_PATH))

    app = PiLightGUI(config_path)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
