"""Shared sysfs brightness helpers for GamePi scripts and the web API."""

from __future__ import annotations

import os
from pathlib import Path

STATE_PATH = Path(os.environ.get("GAMEPI_BRIGHTNESS_STATE", "/var/lib/gamepi/brightness"))
DEFAULT_STEP = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", "10"))


def find_backlight() -> tuple[Path, Path] | None:
    root = Path("/sys/class/backlight")
    if not root.is_dir():
        return None
    for entry in sorted(root.iterdir()):
        brightness = entry / "brightness"
        maximum = entry / "max_brightness"
        if brightness.is_file() and maximum.is_file():
            return brightness, maximum
    return None


def read_int(path: Path, default: int) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return default


def load_level(max_level: int) -> int:
    if STATE_PATH.is_file():
        stored = read_int(STATE_PATH, max_level)
        return max(0, min(stored, max_level))
    return max_level


def store_level(level: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(f"{level}\n", encoding="utf-8")


def apply_level(level: int, brightness_path: Path, max_path: Path) -> int:
    max_level = read_int(max_path, 255)
    clamped = max(0, min(level, max_level))
    brightness_path.write_text(f"{clamped}\n", encoding="utf-8")
    store_level(clamped)
    return clamped


def adjust_brightness(delta: int) -> dict[str, int | bool]:
    backlight = find_backlight()
    if backlight is None:
        return {"ok": False, "available": False}
    brightness_path, max_path = backlight
    max_level = read_int(max_path, 255)
    current = read_int(brightness_path, load_level(max_level))
    level = apply_level(current + delta, brightness_path, max_path)
    return {
        "ok": True,
        "available": True,
        "level": level,
        "max": max_level,
    }


def brightness_status() -> dict[str, int | bool]:
    backlight = find_backlight()
    if backlight is None:
        return {"available": False}
    brightness_path, max_path = backlight
    max_level = read_int(max_path, 255)
    level = read_int(brightness_path, load_level(max_level))
    return {
        "available": True,
        "level": level,
        "max": max_level,
    }
