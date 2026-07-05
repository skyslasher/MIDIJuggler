"""Find GamePi13 gpio-key input devices (per-GPIO button@XX or legacy gpio-keys)."""

from __future__ import annotations

import os

START_CODE = 31  # KEY_S
BRIGHTNESS_DOWN = 224
BRIGHTNESS_UP = 225


def gpio_button_name(gpio: int) -> str:
    return f"button@{gpio:x}"


def _env_gpio(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def find_start_device():
    """Return the evdev device for the Start button, or None."""
    from evdev import InputDevice, ecodes, list_devices

    start_gpio = _env_gpio("GAMEPI_START_GPIO", 26)
    target = gpio_button_name(start_gpio).casefold()
    legacy = None

    for path in list_devices():
        device = InputDevice(path)
        name = device.name.casefold()
        if name == target:
            return device
        if name == "gpio-keys":
            legacy = device

    if legacy is not None and START_CODE in legacy.capabilities().get(ecodes.EV_KEY, []):
        return legacy
    return None


def find_brightness_devices():
    """Return evdev devices for L/R brightness keys (may be one legacy or two GPIO buttons)."""
    from evdev import InputDevice, ecodes, list_devices

    l_name = gpio_button_name(_env_gpio("GAMEPI_L_GPIO", 23)).casefold()
    r_name = gpio_button_name(_env_gpio("GAMEPI_R_GPIO", 14)).casefold()
    by_name: dict[str, InputDevice] = {}
    legacy = None

    for path in list_devices():
        device = InputDevice(path)
        name = device.name.casefold()
        if name in (l_name, r_name):
            by_name[name] = device
        elif name == "gpio-keys":
            legacy = device

    if legacy is not None:
        keys = legacy.capabilities().get(ecodes.EV_KEY, [])
        if BRIGHTNESS_DOWN in keys or BRIGHTNESS_UP in keys:
            return [legacy]

    devices = []
    if l_name in by_name:
        devices.append(by_name[l_name])
    if r_name in by_name:
        devices.append(by_name[r_name])
    return devices
