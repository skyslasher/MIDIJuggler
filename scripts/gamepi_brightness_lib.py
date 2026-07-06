"""Shared brightness helpers for GamePi scripts and the web API."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

STATE_PATH = Path(os.environ.get("GAMEPI_BRIGHTNESS_STATE", "/var/lib/gamepi/brightness"))
DEFAULT_STEP = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", "10"))
SOFTWARE_MAX = int(os.environ.get("GAMEPI_BRIGHTNESS_MAX", "255"))
GAMMA_MIN = float(os.environ.get("GAMEPI_BRIGHTNESS_GAMMA_MIN", "0.12"))
GAMMA_MAX = float(os.environ.get("GAMEPI_BRIGHTNESS_GAMMA_MAX", "1.0"))
APPLY_GAMMA_SCRIPT = Path(
    os.environ.get(
        "GAMEPI_APPLY_GAMMA_SCRIPT",
        "/opt/midijuggler/app/scripts/gamepi-apply-gamma.sh",
    )
)


def _software_brightness_enabled() -> bool:
    value = os.environ.get("GAMEPI_SOFTWARE_BRIGHTNESS", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def find_backlight() -> tuple[Path, Path] | None:
    override = os.environ.get("GAMEPI_BACKLIGHT_BRIGHTNESS", "").strip()
    max_override = os.environ.get("GAMEPI_BACKLIGHT_MAX_BRIGHTNESS", "").strip()
    if override and max_override:
        brightness = Path(override)
        maximum = Path(max_override)
        if brightness.is_file() and maximum.is_file():
            return brightness, maximum

    root = Path("/sys/class/backlight")
    if not root.is_dir():
        return None
    preferred = os.environ.get("GAMEPI_BACKLIGHT_NAME", "").strip()
    entries = sorted(root.iterdir(), key=lambda path: path.name)
    if preferred:
        preferred_path = root / preferred
        if preferred_path.is_dir():
            entries = [preferred_path, *[entry for entry in entries if entry != preferred_path]]
    for entry in entries:
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
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(f"{level}\n", encoding="utf-8")
    except OSError:
        pass


def brightness_mode() -> str:
    if find_backlight() is not None:
        return "sysfs"
    if _software_brightness_enabled():
        return "software"
    return "none"


def level_to_gamma(level: int, max_level: int = SOFTWARE_MAX) -> float:
    if max_level <= 0:
        return GAMMA_MAX
    ratio = max(0.0, min(level / max_level, 1.0))
    return GAMMA_MIN + ratio * (GAMMA_MAX - GAMMA_MIN)


def apply_software_level(level: int, max_level: int = SOFTWARE_MAX) -> tuple[int, bool]:
    clamped = max(0, min(level, max_level))
    gamma = level_to_gamma(clamped, max_level)
    if not _run_gamma(gamma):
        return load_level(max_level), False
    store_level(clamped)
    return clamped, True


def _run_gamma(gamma: float) -> bool:
    if not APPLY_GAMMA_SCRIPT.is_file():
        return False
    if os.geteuid() == 0:
        command = [str(APPLY_GAMMA_SCRIPT), f"{gamma:.4f}"]
    else:
        command = ["sudo", "-n", str(APPLY_GAMMA_SCRIPT), f"{gamma:.4f}"]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def apply_level(level: int, brightness_path: Path, max_path: Path) -> int:
    max_level = read_int(max_path, SOFTWARE_MAX)
    clamped = max(0, min(level, max_level))
    try:
        brightness_path.write_text(f"{clamped}\n", encoding="utf-8")
    except OSError:
        return load_level(max_level)
    store_level(clamped)
    return clamped


def adjust_brightness(delta: int) -> dict[str, int | bool | str]:
    backlight = find_backlight()
    if backlight is not None:
        brightness_path, max_path = backlight
        max_level = read_int(max_path, SOFTWARE_MAX)
        current = read_int(brightness_path, load_level(max_level))
        level = apply_level(current + delta, brightness_path, max_path)
        return {
            "ok": True,
            "available": True,
            "mode": "sysfs",
            "level": level,
            "max": max_level,
        }

    if not _software_brightness_enabled():
        return {"ok": False, "available": False, "mode": "none"}

    max_level = SOFTWARE_MAX
    current = load_level(max_level)
    level, ok = apply_software_level(current + delta, max_level)
    return {
        "ok": ok,
        "available": True,
        "mode": "software",
        "level": level,
        "max": max_level,
    }


def brightness_status() -> dict[str, int | bool | str]:
    backlight = find_backlight()
    if backlight is not None:
        brightness_path, max_path = backlight
        max_level = read_int(max_path, SOFTWARE_MAX)
        level = read_int(brightness_path, load_level(max_level))
        return {
            "available": True,
            "mode": "sysfs",
            "level": level,
            "max": max_level,
        }

    if not _software_brightness_enabled():
        return {"available": False, "mode": "none"}

    max_level = SOFTWARE_MAX
    return {
        "available": True,
        "mode": "software",
        "level": load_level(max_level),
        "max": max_level,
    }
