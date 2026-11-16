"""Run the simulator: ``python -m backend.simulation --help``."""

import io
import sys

from .cli import main

if __name__ == "__main__":
    # Windows consoles and pipes may default to a legacy code page.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    sys.exit(main())
