#!/usr/bin/env python3
"""Adjust display brightness when GamePi L/R keys emit brightness scancodes."""

from __future__ import annotations

import logging
import os
import select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_brightness_lib import DEFAULT_STEP, adjust_brightness, brightness_mode, brightness_status
from gamepi_gpio_keys import BRIGHTNESS_DOWN, BRIGHTNESS_UP, find_brightness_devices

LOGGER = logging.getLogger("gamepi-brightness")
STEP = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", str(DEFAULT_STEP)))


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _adjust(delta: int) -> None:
    result = adjust_brightness(delta)
    if result.get("ok"):
        LOGGER.info(
            "brightness set to %s/%s (%s)",
            result["level"],
            result["max"],
            result.get("mode", "unknown"),
        )
    elif not result.get("available"):
        LOGGER.warning("brightness not available (mode=%s)", result.get("mode", "none"))


def _handle_event(event) -> None:
    if event.type != 1 or event.value != 1:
        return
    if event.code == BRIGHTNESS_DOWN:
        _adjust(-STEP)
    elif event.code == BRIGHTNESS_UP:
        _adjust(STEP)


def main() -> int:
    _configure_logging()
    mode = brightness_mode()
    if mode == "none":
        LOGGER.warning(
            "no backlight device and software brightness disabled; "
            "set GAMEPI_SOFTWARE_BRIGHTNESS=1 or add /sys/class/backlight"
        )
        return 0

    LOGGER.info("brightness mode: %s", mode)
    status = brightness_status()
    if status.get("available"):
        LOGGER.info("initial brightness %s/%s", status.get("level"), status.get("max"))

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

    fds = {device.fd: device for device in devices}
    while True:
        ready, _, _ = select.select(fds.keys(), [], [])
        for fd in ready:
            device = fds[fd]
            for event in device.read():
                _handle_event(event)


if __name__ == "__main__":
    raise SystemExit(main())
