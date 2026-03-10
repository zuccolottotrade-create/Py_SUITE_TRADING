from __future__ import annotations

import sys

from .cli import main
from . import run_selftest


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        run_selftest()
        print("SELFTEST OK")
        raise SystemExit(0)

    raise SystemExit(main())