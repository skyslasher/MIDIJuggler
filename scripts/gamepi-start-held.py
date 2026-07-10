#!/usr/bin/env python3
"""Return 0 when the GamePi Start key is held."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_gpio_keys import START_CODE, ensure_device_nonblocking, find_start_device


def _wait_for_press(device, detect_s: float) -> bool:
    press_deadline = time.monotonic() + detect_s
    while time.monotonic() < press_deadline:
        if START_CODE in device.active_keys():
            return True
        try:
            for event in device.read():
                if event.type == 1 and event.code == START_CODE and event.value == 1:
                    return True
        except BlockingIOError:
            pass
        if START_CODE in device.active_keys():
            return True
        time.sleep(0.02)
    return False


def _wait_for_hold(device, hold_s: float) -> bool:
    held_since = time.monotonic()
    while time.monotonic() - held_since < hold_s:
        if START_CODE not in device.active_keys():
            return False
        try:
            for event in device.read():
                if event.type == 1 and event.code == START_CODE and event.value == 0:
                    return False
        except BlockingIOError:
            pass
        time.sleep(0.02)
    return True


def main() -> int:
    hold_ms = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    detect_ms = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    hold_s = hold_ms / 1000.0
    detect_s = detect_ms / 1000.0

    try:
        device = None
        detect_deadline = time.monotonic() + detect_s
        while device is None and time.monotonic() < detect_deadline:
            device = find_start_device()
            if device is None:
                time.sleep(0.05)
    except ImportError:
        return 1
    except OSError as exc:
        print(f"gamepi-start-held: input device error: {exc}", file=sys.stderr)
        return 1

    if device is None:
        return 1

    try:
        ensure_device_nonblocking(device)
    except OSError as exc:
        print(f"gamepi-start-held: non-blocking setup failed: {exc}", file=sys.stderr)
        return 1

    if not _wait_for_press(device, detect_s):
        return 1

    if not _wait_for_hold(device, hold_s):
        return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — fail closed for kiosk handoff
        print(f"gamepi-start-held: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
