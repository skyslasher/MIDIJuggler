#!/usr/bin/env python3
"""Adjust display brightness when GamePi L/R keys emit brightness scancodes."""

from __future__ import annotations

import logging
import select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_brightness_lib import adjust_brightness, brightness_mode, sync_brightness
from gamepi_gpio_keys import brightness_delta_for_event, find_brightness_devices

LOGGER = logging.getLogger("gamepi-brightness")


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
    elif result.get("available"):
        LOGGER.error(
            "brightness apply failed (mode=%s level=%s)",
            result.get("mode", "unknown"),
            result.get("level"),
        )
    else:
        LOGGER.warning("brightness not available (mode=%s)", result.get("mode", "none"))


def _handle_event(event, device) -> None:
    delta = brightness_delta_for_event(device, event)
    if delta is not None:
        _adjust(delta)


def main() -> int:
    _configure_logging()
    mode = brightness_mode()
    if mode == "none":
        LOGGER.warning(
            "no brightness backend available; install rpi-lgpio or enable /sys/class/backlight"
        )
        return 0

    LOGGER.info("brightness mode: %s", mode)
    initial = sync_brightness()
    if initial.get("ok"):
        LOGGER.info("initial brightness %s/%s", initial.get("level"), initial.get("max"))
    else:
        LOGGER.error("initial brightness apply failed (mode=%s)", initial.get("mode"))

    try:
        devices = find_brightness_devices()
    except ImportError:
        LOGGER.error("python-evdev is required")
        return 1
    if not devices:
        LOGGER.error("GamePi brightness input devices not found (GPL/GPR or button@17 / button@e)")
        return 1

    for device in devices:
        LOGGER.info("listening on %s (%s)", device.path, device.name)

    fds = {device.fd: device for device in devices}
    while True:
        ready, _, _ = select.select(fds.keys(), [], [])
        for fd in ready:
            device = fds[fd]
            for event in device.read():
                _handle_event(event, device)


if __name__ == "__main__":
    raise SystemExit(main())
