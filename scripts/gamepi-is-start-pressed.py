#!/usr/bin/env python3
"""Return 0 when the GamePi Start key (gpio-keys KEY_S) is currently pressed."""

from __future__ import annotations

import sys

START_CODE = 31  # KEY_S


def _find_keyboard():
    from evdev import InputDevice, list_devices

    for path in list_devices():
        device = InputDevice(path)
        if "gpio-keys" in device.name.casefold():
            return device
    return None


def main() -> int:
    try:
        device = _find_keyboard()
    except ImportError:
        return 1

    if device is None:
        return 1

    return 0 if START_CODE in device.active_keys() else 1


if __name__ == "__main__":
    raise SystemExit(main())
