"""PWM backlight control for GamePi13 (Waveshare ST7789)."""

from __future__ import annotations

import os
from pathlib import Path

from gamepi_lgpio_env import prepare_lgpio_runtime

_PWM_HANDLE: tuple[int, int, int] | None = None  # chip, handle, gpio
_LAST_ERROR = ""
PIN_STATE_PATH = Path(os.environ.get("GAMEPI_BACKLIGHT_GPIO_STATE", "/var/lib/gamepi/backlight-gpio"))


def last_pwm_error() -> str:
    return _LAST_ERROR


def _backlight_pwm_frequency() -> int:
    return int(os.environ.get("GAMEPI_BACKLIGHT_PWM_HZ", "2000"))


def _gpio_candidates() -> list[int]:
    raw = os.environ.get("GAMEPI_BACKLIGHT_GPIO_CANDIDATES", "24,18")
    pins = [int(part.strip()) for part in raw.split(",") if part.strip()]
    saved = _load_saved_gpio()
    if saved is not None and saved not in pins:
        return [saved, *pins]
    if saved is not None:
        return [saved, *[pin for pin in pins if pin != saved]]
    if os.environ.get("GAMEPI_BACKLIGHT_GPIO"):
        preferred = int(os.environ["GAMEPI_BACKLIGHT_GPIO"])
        return [preferred, *[pin for pin in pins if pin != preferred]]
    return pins


def _load_saved_gpio() -> int | None:
    try:
        if PIN_STATE_PATH.is_file():
            return int(PIN_STATE_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return None


def _store_saved_gpio(gpio: int) -> None:
    try:
        PIN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PIN_STATE_PATH.write_text(f"{gpio}\n", encoding="utf-8")
    except OSError:
        pass


def _resolve_gpiochip() -> int:
    configured = os.environ.get("GAMEPI_BACKLIGHT_GPIO_CHIP", "auto").strip()
    if configured and configured != "auto":
        return int(configured)
    prepare_lgpio_runtime()
    import lgpio

    for chip in (0, 4, 10):
        try:
            handle = lgpio.gpiochip_open(chip)
            lgpio.gpiochip_close(handle)
            return chip
        except Exception:
            continue
    return 0


def _set_error(message: str) -> None:
    global _LAST_ERROR
    _LAST_ERROR = message


def pwm_available() -> bool:
    if os.environ.get("GAMEPI_PWM_BACKLIGHT", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    try:
        prepare_lgpio_runtime()
        import lgpio  # noqa: F401
    except ImportError:
        _set_error("lgpio not installed")
        return False
    except OSError as exc:
        _set_error(str(exc))
        return False
    return True


def _apply_on_pin(handle: int, gpio: int, duty: int, frequency: int, lgpio) -> None:
    if duty <= 0:
        try:
            lgpio.tx_pwm(handle, gpio, frequency, 0, 0)
        except Exception:
            pass
        lgpio.gpio_claim_output(handle, gpio, level=0)
        lgpio.gpio_write(handle, gpio, 0)
        return
    lgpio.gpio_claim_output(handle, gpio)
    lgpio.tx_pwm(handle, gpio, frequency, duty, 0)


def apply_pwm_level(level: int, max_level: int = 255) -> bool:
    global _PWM_HANDLE

    if max_level <= 0:
        _set_error("invalid max_level")
        return False

    try:
        prepare_lgpio_runtime()
        import lgpio
    except ImportError:
        _set_error("lgpio not installed")
        return False
    except OSError as exc:
        _set_error(str(exc))
        return False

    duty = max(0, min(int(round((level / max_level) * 100)), 100))
    frequency = _backlight_pwm_frequency()
    chip = _resolve_gpiochip()
    errors: list[str] = []

    if _PWM_HANDLE is not None:
        saved_chip, handle, gpio = _PWM_HANDLE
        try:
            _apply_on_pin(handle, gpio, duty, frequency, lgpio)
            return True
        except Exception as exc:
            errors.append(f"gpio {gpio}: {exc}")
            try:
                lgpio.gpiochip_close(handle)
            except Exception:
                pass
            _PWM_HANDLE = None

    for gpio in _gpio_candidates():
        handle = None
        try:
            handle = lgpio.gpiochip_open(chip)
            _apply_on_pin(handle, gpio, duty, frequency, lgpio)
            _PWM_HANDLE = (chip, handle, gpio)
            _store_saved_gpio(gpio)
            _set_error("")
            return True
        except Exception as exc:
            errors.append(f"gpio {gpio}: {exc}")
            if handle is not None:
                try:
                    lgpio.gpiochip_close(handle)
                except Exception:
                    pass

    _PWM_HANDLE = None
    _set_error("; ".join(errors) if errors else "pwm apply failed")
    return False


def close_pwm() -> None:
    global _PWM_HANDLE
    if _PWM_HANDLE is None:
        return
    try:
        prepare_lgpio_runtime()
        import lgpio

        chip, handle, gpio = _PWM_HANDLE
        _apply_on_pin(handle, gpio, 0, _backlight_pwm_frequency(), lgpio)
        lgpio.gpiochip_close(handle)
    except Exception:
        pass
    _PWM_HANDLE = None
