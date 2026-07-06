"""Shared brightness helpers for GamePi scripts and the web API."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from gamepi_backlight_pwm import apply_pwm_level, pwm_available

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
    if pwm_available():
        return "pwm"
    if _software_brightness_enabled():
        return "software"
    return "none"


def level_to_gamma(level: int, max_level: int = SOFTWARE_MAX) -> float:
    if max_level <= 0:
        return GAMMA_MAX
    ratio = max(0.0, min(level / max_level, 1.0))
    return GAMMA_MIN + ratio * (GAMMA_MAX - GAMMA_MIN)


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


def apply_level_value(level: int, max_level: int = SOFTWARE_MAX) -> tuple[int, bool, str]:
    clamped = max(0, min(level, max_level))

    backlight = find_backlight()
    if backlight is not None:
        brightness_path, max_path = backlight
        sysfs_max = read_int(max_path, max_level)
        applied = apply_level(clamped, brightness_path, max_path)
        return applied, True, "sysfs"

    if pwm_available():
        if apply_pwm_level(clamped, max_level):
            store_level(clamped)
            return clamped, True, "pwm"
        return load_level(max_level), False, "pwm"

    if _software_brightness_enabled():
        gamma = level_to_gamma(clamped, max_level)
        if _run_gamma(gamma):
            store_level(clamped)
            return clamped, True, "software"
        return load_level(max_level), False, "software"

    return load_level(max_level), False, "none"


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
    max_level = SOFTWARE_MAX
    if find_backlight() is not None:
        max_path = find_backlight()[1]
        max_level = read_int(max_path, SOFTWARE_MAX)

    current = load_level(max_level)
    level, ok, mode = apply_level_value(current + delta, max_level)
    available = mode != "none"
    return {
        "ok": ok,
        "available": available,
        "mode": mode,
        "level": level,
        "max": max_level,
    }


def sync_brightness() -> dict[str, int | bool | str]:
    max_level = SOFTWARE_MAX
    if find_backlight() is not None:
        max_path = find_backlight()[1]
        max_level = read_int(max_path, SOFTWARE_MAX)
    level, ok, mode = apply_level_value(load_level(max_level), max_level)
    return {
        "ok": ok,
        "available": mode != "none",
        "mode": mode,
        "level": level,
        "max": max_level,
    }


def brightness_status() -> dict[str, int | bool | str]:
    mode = brightness_mode()
    if mode == "none":
        return {"available": False, "mode": "none"}

    max_level = SOFTWARE_MAX
    if mode == "sysfs":
        backlight = find_backlight()
        assert backlight is not None
        brightness_path, max_path = backlight
        max_level = read_int(max_path, SOFTWARE_MAX)
        level = read_int(brightness_path, load_level(max_level))
        return {
            "available": True,
            "mode": "sysfs",
            "level": level,
            "max": max_level,
        }

    return {
        "available": True,
        "mode": mode,
        "level": load_level(max_level),
        "max": max_level,
    }
