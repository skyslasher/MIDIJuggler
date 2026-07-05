#!/usr/bin/env python3
"""Return 0 when the GamePi Start key is held (gpio-keys KEY_S)."""

from __future__ import annotations

import sys
import time

START_CODE = 31  # KEY_S


def _find_keyboard():
    from evdev import InputDevice, list_devices

    for path in list_devices():
        device = InputDevice(path)
        if "gpio-keys" in device.name.casefold():
            return device
    return None


def main() -> int:
    hold_ms = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    hold_s = hold_ms / 1000.0

    try:
        device = _find_keyboard()
    except ImportError:
        return 1
    if device is None:
        return 1

    device.setblocking(False)

    if START_CODE not in device.active_keys():
        deadline = time.monotonic() + 0.15
        while time.monotonic() < deadline:
            if START_CODE in device.active_keys():
                break
            try:
                for event in device.read():
                    if event.type == 1 and event.code == START_CODE and event.value == 1:
                        break
            except BlockingIOError:
                pass
            time.sleep(0.02)
        if START_CODE not in device.active_keys():
            return 1

    held_since = time.monotonic()
    while time.monotonic() - held_since < hold_s:
        if START_CODE not in device.active_keys():
            return 1
        try:
            for event in device.read():
                if event.type == 1 and event.code == START_CODE and event.value == 0:
                    return 1
        except BlockingIOError:
            pass
        time.sleep(0.02)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
