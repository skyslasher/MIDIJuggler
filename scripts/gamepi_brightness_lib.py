"""Shared brightness helpers for GamePi scripts and the web API."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from gamepi_backlight_pwm import apply_pwm_level, last_pwm_error, pwm_available

STATE_PATH = Path(os.environ.get("GAMEPI_BRIGHTNESS_STATE", "/var/lib/gamepi/brightness"))
DEFAULT_STEP = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", "10"))
DEFAULT_LEVEL = int(os.environ.get("GAMEPI_BRIGHTNESS_DEFAULT", "200"))
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


def _is_non_panel_led(name: str) -> bool:
    lowered = name.casefold()
    if lowered in {"default-on", "act", "pwr"}:
        return True
    return lowered.startswith("mmc")


def _usable_sysfs_max(max_path: Path) -> int | None:
    if not max_path.is_file():
        return None
    max_level = read_int(max_path, 0)
    if max_level <= 1:
        return None
    return max_level


def find_backlight() -> tuple[Path, Path] | None:
    override = os.environ.get("GAMEPI_BACKLIGHT_BRIGHTNESS", "").strip()
    max_override = os.environ.get("GAMEPI_BACKLIGHT_MAX_BRIGHTNESS", "").strip()
    if override and max_override:
        brightness = Path(override)
        maximum = Path(max_override)
        if brightness.is_file() and maximum.is_file():
            return brightness, maximum

    found = _scan_backlight_dir(Path("/sys/class/backlight"))
    if found is not None:
        return found

    return _scan_leds_dir(Path("/sys/class/leds"))


def _scan_backlight_dir(root: Path) -> tuple[Path, Path] | None:
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
        if brightness.is_file() and maximum.is_file() and _usable_sysfs_max(maximum) is not None:
            return brightness, maximum
    return None


def _scan_leds_dir(root: Path) -> tuple[Path, Path] | None:
    if not root.is_dir():
        return None
    preferred_names = ("backlight", "lcd", "fb", "st7789", "waveshare", "bl", "panel")
    entries = sorted(root.iterdir(), key=lambda path: path.name)
    for name in preferred_names:
        for entry in entries:
            if name in entry.name.casefold():
                found = _led_brightness_paths(entry)
                if found is not None:
                    return found
    for entry in entries:
        found = _led_brightness_paths(entry)
        if found is not None:
            return found
    return None


def _led_brightness_paths(entry: Path) -> tuple[Path, Path] | None:
    if _is_non_panel_led(entry.name):
        return None
    brightness = entry / "brightness"
    if not brightness.is_file():
        return None
    maximum = entry / "max_brightness"
    if maximum.is_file():
        if _usable_sysfs_max(maximum) is None:
            return None
        return brightness, maximum
    return brightness, brightness


def read_int(path: Path, default: int) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return default


def load_level(max_level: int) -> int:
    if STATE_PATH.is_file():
        stored = read_int(STATE_PATH, DEFAULT_LEVEL)
        return max(0, min(stored, max_level))
    return min(DEFAULT_LEVEL, max_level)


def store_level(level: int) -> bool:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(f"{level}\n", encoding="utf-8")
        return True
    except OSError:
        return False


def brightness_mode() -> str:
    if find_backlight() is not None:
        return "sysfs"
    if _software_brightness_enabled():
        return "software"
    if pwm_available() and os.environ.get("GAMEPI_PWM_BACKLIGHT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return "pwm"
    return "none"


def level_to_gamma(level: int, max_level: int = SOFTWARE_MAX) -> float:
    if max_level <= 0:
        return GAMMA_MAX
    ratio = max(0.0, min(level / max_level, 1.0))
    return GAMMA_MIN + ratio * (GAMMA_MAX - GAMMA_MIN)


def _run_display_brightness(gamma: float) -> bool:
    """Best-effort X/fbdev dimming; may have no visible effect on SPI panels."""
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


def _skip_x_brightness() -> bool:
    value = os.environ.get("GAMEPI_SKIP_X_BRIGHTNESS", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _run_gamma(gamma: float) -> bool:
    return _run_display_brightness(gamma)


def apply_level_value(level: int, max_level: int = SOFTWARE_MAX) -> tuple[int, bool, str]:
    clamped = max(0, min(level, max_level))

    backlight = find_backlight()
    if backlight is not None:
        brightness_path, max_path = backlight
        sysfs_max = read_int(max_path, max_level)
        applied = apply_level(clamped, brightness_path, max_path)
        return applied, True, "sysfs"

    if pwm_available() and os.environ.get("GAMEPI_PWM_BACKLIGHT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        if apply_pwm_level(clamped, max_level):
            store_level(clamped)
            return clamped, True, "pwm"
        return load_level(max_level), False, "pwm"

    if _software_brightness_enabled():
        if not store_level(clamped):
            return load_level(max_level), False, "software"
        if not _skip_x_brightness():
            gamma = level_to_gamma(clamped, max_level)
            _run_display_brightness(gamma)
        # Visible dimming on GamePi13 is done in the kiosk UI (CSS filter); X/fbdev
        # helpers above are best-effort and often no-op on the SPI panel.
        return clamped, True, "software"

    return load_level(max_level), False, "none"


def apply_level(level: int, brightness_path: Path, max_path: Path) -> int:
    if max_path == brightness_path:
        max_level = SOFTWARE_MAX
    else:
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

    previous = load_level(max_level)
    requested = max(0, min(previous + delta, max_level))
    level, ok, mode = apply_level_value(requested, max_level)
    available = mode != "none"
    payload: dict[str, int | bool | str] = {
        "ok": ok,
        "available": available,
        "mode": mode,
        "level": level,
        "max": max_level,
        "previous": previous,
        "requested": requested,
        "delta": delta,
    }
    if mode == "pwm" and not ok:
        error = last_pwm_error()
        if error:
            payload["error"] = error
    return payload


def set_brightness(level: int) -> dict[str, int | bool | str]:
    max_level = SOFTWARE_MAX
    if find_backlight() is not None:
        max_path = find_backlight()[1]
        max_level = read_int(max_path, SOFTWARE_MAX)
    previous = load_level(max_level)
    requested = max(0, min(level, max_level))
    applied, ok, mode = apply_level_value(requested, max_level)
    payload: dict[str, int | bool | str] = {
        "ok": ok,
        "available": mode != "none",
        "mode": mode,
        "level": applied,
        "max": max_level,
        "previous": previous,
        "requested": requested,
    }
    if mode == "pwm" and not ok:
        error = last_pwm_error()
        if error:
            payload["error"] = error
    return payload


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
        if max_path == brightness_path:
            max_level = SOFTWARE_MAX
        else:
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
