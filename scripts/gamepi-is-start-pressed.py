#!/usr/bin/env python3
"""Return 0 when the GamePi Start key is currently pressed."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_gpio_keys import START_CODE, find_start_device


def main() -> int:
    try:
        device = find_start_device()
    except ImportError:
        return 1

    if device is None:
        return 1

    return 0 if START_CODE in device.active_keys() else 1


if __name__ == "__main__":
    raise SystemExit(main())
