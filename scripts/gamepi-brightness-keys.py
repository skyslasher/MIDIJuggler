#!/usr/bin/env python3
"""Adjust display brightness when GamePi L/R keys emit brightness scancodes."""

from __future__ import annotations

import logging
import os
import select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamepi_gpio_keys import BRIGHTNESS_DOWN, BRIGHTNESS_UP, find_brightness_devices

LOGGER = logging.getLogger("gamepi-brightness")
STATE_PATH = Path(os.environ.get("GAMEPI_BRIGHTNESS_STATE", "/var/lib/gamepi/brightness"))
STEP = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", "10"))


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


def _adjust(delta: int, backlight: tuple[Path, Path]) -> None:
    brightness_path, max_path = backlight
    max_level = _read_int(max_path, 255)
    current = _read_int(brightness_path, _load_level(max_level))
    _apply_level(current + delta, brightness_path, max_path)


def _handle_event(event, backlight: tuple[Path, Path]) -> None:
    if event.type != 1 or event.value != 1:
        return
    if event.code == BRIGHTNESS_DOWN:
        _adjust(-STEP, backlight)
    elif event.code == BRIGHTNESS_UP:
        _adjust(STEP, backlight)


def main() -> int:
    _configure_logging()
    backlight = _find_backlight()
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
    max_level = _read_int(max_path, 255)
    _apply_level(_load_level(max_level), backlight[0], max_path)

    fds = {device.fd: device for device in devices}
    while True:
        ready, _, _ = select.select(fds.keys(), [], [])
        for fd in ready:
            device = fds[fd]
            for event in device.read():
                _handle_event(event, backlight)


if __name__ == "__main__":
    raise SystemExit(main())
