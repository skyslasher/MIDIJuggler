"""PWM backlight control for GamePi13 (Waveshare ST7789, default GPIO 18)."""

from __future__ import annotations

import os

_PWM_HANDLE: tuple[int, int] | None = None


def _backlight_gpio() -> int:
    return int(os.environ.get("GAMEPI_BACKLIGHT_GPIO", "18"))


def _backlight_chip() -> int:
    return int(os.environ.get("GAMEPI_BACKLIGHT_GPIO_CHIP", "0"))


def _backlight_pwm_frequency() -> int:
    return int(os.environ.get("GAMEPI_BACKLIGHT_PWM_HZ", "2000"))


def pwm_available() -> bool:
    if os.environ.get("GAMEPI_PWM_BACKLIGHT", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    try:
        import lgpio  # noqa: F401
    except ImportError:
        return False
    return True


def apply_pwm_level(level: int, max_level: int = 255) -> bool:
    global _PWM_HANDLE

    try:
        import lgpio
    except ImportError:
        return False

    if max_level <= 0:
        return False

    duty = max(0, min(int(round((level / max_level) * 100)), 100))
    gpio = _backlight_gpio()
    chip = _backlight_chip()
    frequency = _backlight_pwm_frequency()

    try:
        if _PWM_HANDLE is None:
            handle = lgpio.gpiochip_open(chip)
            _PWM_HANDLE = (handle, gpio)
        else:
            handle, _ = _PWM_HANDLE

        if duty <= 0:
            lgpio.tx_pwm(handle, gpio, frequency, 0, 0)
            lgpio.gpio_write(handle, gpio, 0)
        else:
            lgpio.tx_pwm(handle, gpio, frequency, duty, 0)
        return True
    except Exception:
        _PWM_HANDLE = None
        return False


def close_pwm() -> None:
    global _PWM_HANDLE
    if _PWM_HANDLE is None:
        return
    try:
        import lgpio

        handle, gpio = _PWM_HANDLE
        lgpio.tx_pwm(handle, gpio, _backlight_pwm_frequency(), 0, 0)
        lgpio.gpiochip_close(handle)
    except Exception:
        pass
    _PWM_HANDLE = None
