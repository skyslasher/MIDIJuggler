#!/usr/bin/env python3
"""Diagnose GamePi brightness inputs and PWM backends."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_lgpio_env import prepare_lgpio_runtime

prepare_lgpio_runtime()

from gamepi_backlight_pwm import _gpio_candidates, apply_pwm_level, last_pwm_error, pwm_available
from gamepi_brightness_lib import brightness_status, set_brightness
from gamepi_gpio_keys import (
    brightness_input_warnings,
    describe_input_devices,
    find_brightness_devices,
)


def main() -> int:
    payload = {
        "brightness_status": brightness_status(),
        "pwm_available": pwm_available(),
        "pwm_candidates": _gpio_candidates(),
        "warnings": brightness_input_warnings(),
        "brightness_devices": [
            {
                "path": device.path,
                "name": device.name,
                "keys": sorted(device.capabilities().get(1, [])),
            }
            for device in find_brightness_devices()
        ],
        "input_devices": describe_input_devices(),
    }
    print(json.dumps(payload, indent=2))

    if "--apply-test" in sys.argv:
        for level in (64, 200, 255):
            result = set_brightness(level)
            print(json.dumps({"apply_test": level, **result}, indent=2))
            if not result.get("ok"):
                print(f"pwm error: {last_pwm_error()}", file=sys.stderr)
                return 1
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
