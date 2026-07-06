#!/usr/bin/env python3
"""Adjust GamePi display brightness once (CLI for web API and shell use)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_lgpio_env import prepare_lgpio_runtime

prepare_lgpio_runtime()

from gamepi_brightness_lib import DEFAULT_STEP, adjust_brightness, brightness_status


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--status":
        print(json.dumps(brightness_status()))
        return 0

    delta = DEFAULT_STEP
    if len(sys.argv) >= 3 and sys.argv[1] == "--delta":
        delta = int(sys.argv[2])
    elif len(sys.argv) >= 2:
        delta = int(sys.argv[1])

    result = adjust_brightness(delta)
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
