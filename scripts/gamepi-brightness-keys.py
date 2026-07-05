#!/usr/bin/env python3
"""Adjust display brightness when GamePi L/R keys emit brightness scancodes."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

LOGGER = logging.getLogger("gamepi-brightness")
STATE_PATH = Path(os.environ.get("GAMEPI_BRIGHTNESS_STATE", "/var/lib/gamepi/brightness"))
STEP = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", "10"))
BRIGHTNESS_DOWN = 224
BRIGHTNESS_UP = 225


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _find_backlight() -> tuple[Path, Path] | None:
    root = Path("/sys/class/backlight")
    if not root.is_dir():
        return None
    for entry in sorted(root.iterdir()):
        brightness = entry / "brightness"
        maximum = entry / "max_brightness"
        if brightness.is_file() and maximum.is_file():
            return brightness, maximum
    return None


def _read_int(path: Path, default: int) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return default


def _load_level(max_level: int) -> int:
    if STATE_PATH.is_file():
        stored = _read_int(STATE_PATH, max_level)
        return max(0, min(stored, max_level))
    return max_level


def _store_level(level: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(f"{level}\n", encoding="utf-8")


def _apply_level(level: int, brightness_path: Path, max_path: Path) -> None:
    max_level = _read_int(max_path, 255)
    clamped = max(0, min(level, max_level))
    brightness_path.write_text(f"{clamped}\n", encoding="utf-8")
    _store_level(clamped)
    LOGGER.info("brightness set to %s/%s", clamped, max_level)


def _find_keyboard():
    from evdev import InputDevice, list_devices

    for path in list_devices():
        device = InputDevice(path)
        if "gpio-keys" in device.name.casefold():
            return device
    return None


def _adjust(delta: int, backlight: tuple[Path, Path]) -> None:
    brightness_path, max_path = backlight
    max_level = _read_int(max_path, 255)
    current = _read_int(brightness_path, _load_level(max_level))
    _apply_level(current + delta, brightness_path, max_path)


def main() -> int:
    _configure_logging()
    backlight = _find_backlight()
    if backlight is None:
        LOGGER.warning(
            "no /sys/class/backlight device found; L/R keys will not change hardware brightness"
        )
        return 0

    try:
        device = _find_keyboard()
    except ImportError:
        LOGGER.error("python-evdev is required")
        return 1
    if device is None:
        LOGGER.error("gpio-keys input device not found")
        return 1

    LOGGER.info("listening on %s (%s)", device.path, device.name)
    max_path = backlight[1]
    max_level = _read_int(max_path, 255)
    _apply_level(_load_level(max_level), backlight[0], max_path)

    for event in device.read_loop():
        if event.type != 1 or event.value != 1:
            continue
        if event.code == BRIGHTNESS_DOWN:
            _adjust(-STEP, backlight)
        elif event.code == BRIGHTNESS_UP:
            _adjust(STEP, backlight)


if __name__ == "__main__":
    raise SystemExit(main())
