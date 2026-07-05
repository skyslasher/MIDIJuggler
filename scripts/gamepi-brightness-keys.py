#!/usr/bin/env python3
"""Adjust display brightness when GamePi L/R keys emit brightness scancodes."""

from __future__ import annotations

import logging
import os
import select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_brightness_lib import DEFAULT_STEP, adjust_brightness, apply_level, find_backlight, load_level, read_int
from gamepi_gpio_keys import BRIGHTNESS_DOWN, BRIGHTNESS_UP, find_brightness_devices

LOGGER = logging.getLogger("gamepi-brightness")
STEP = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", str(DEFAULT_STEP)))


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _adjust(delta: int, backlight: tuple[Path, Path]) -> None:
    result = adjust_brightness(delta)
    if result.get("ok"):
        LOGGER.info("brightness set to %s/%s", result["level"], result["max"])


def _handle_event(event, backlight: tuple[Path, Path]) -> None:
    if event.type != 1 or event.value != 1:
        return
    if event.code == BRIGHTNESS_DOWN:
        _adjust(-STEP, backlight)
    elif event.code == BRIGHTNESS_UP:
        _adjust(STEP, backlight)


def main() -> int:
    _configure_logging()
    backlight = find_backlight()
    if backlight is None:
        LOGGER.warning(
            "no /sys/class/backlight device found; L/R keys will not change hardware brightness"
        )
        return 0

    try:
        devices = find_brightness_devices()
    except ImportError:
        LOGGER.error("python-evdev is required")
        return 1
    if not devices:
        LOGGER.error("GamePi brightness input devices not found (button@17 / button@e or gpio-keys)")
        return 1

    for device in devices:
        LOGGER.info("listening on %s (%s)", device.path, device.name)

    max_path = backlight[1]
    max_level = read_int(max_path, 255)
    apply_level(load_level(max_level), backlight[0], max_path)

    fds = {device.fd: device for device in devices}
    while True:
        ready, _, _ = select.select(fds.keys(), [], [])
        for fd in ready:
            device = fds[fd]
            for event in device.read():
                _handle_event(event, backlight)


if __name__ == "__main__":
    raise SystemExit(main())
