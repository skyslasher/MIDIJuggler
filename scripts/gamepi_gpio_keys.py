"""Find GamePi13 gpio-key input devices (per-GPIO button@XX or legacy gpio-keys)."""

from __future__ import annotations

import os

START_CODE = 31  # KEY_S
BRIGHTNESS_DOWN = 224
BRIGHTNESS_UP = 225


def gpio_button_name(gpio: int) -> str:
    """Kernel names per-GPIO buttons with the GPIO number in hex: GPIO 14 -> button@e."""
    return f"button@{gpio:x}"


def _env_gpio(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def brightness_button_names() -> tuple[str, str, set[str], set[str]]:
    l_gpio = _env_gpio("GAMEPI_L_GPIO", 23)
    r_gpio = _env_gpio("GAMEPI_R_GPIO", 14)
    down_names = {gpio_button_name(l_gpio), "gpl"}
    up_names = {gpio_button_name(r_gpio), "gpr"}
    for label in os.environ.get("GAMEPI_L_LABELS", "GPL").split(","):
        if label.strip():
            down_names.add(label.strip().casefold())
    for label in os.environ.get("GAMEPI_R_LABELS", "GPR").split(","):
        if label.strip():
            up_names.add(label.strip().casefold())
    return gpio_button_name(l_gpio), gpio_button_name(r_gpio), down_names, up_names


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


def _device_is_brightness(device, down_names: set[str], up_names: set[str]) -> bool:
    from evdev import ecodes

    name = device.name.casefold()
    keys = set(device.capabilities().get(ecodes.EV_KEY, []))
    if name in down_names and BRIGHTNESS_DOWN in keys:
        return True
    if name in up_names and BRIGHTNESS_UP in keys:
        return True
    return False


def find_brightness_devices():
    """Return evdev devices for L/R brightness keys (may be one legacy or two GPIO buttons)."""
    from evdev import InputDevice, list_devices

    _, _, down_names, up_names = brightness_button_names()
    matched: list[InputDevice] = []
    seen: set[str] = set()
    legacy = None

    for path in list_devices():
        device = InputDevice(path)
        name = device.name.casefold()
        if name == "gpio-keys":
            legacy = device
            continue
        if _device_is_brightness(device, down_names, up_names):
            if path not in seen:
                matched.append(device)
                seen.add(path)

    if legacy is not None:
        keys = legacy.capabilities().get(1, [])
        if BRIGHTNESS_DOWN in keys or BRIGHTNESS_UP in keys:
            return [legacy]

    return matched


def brightness_delta_for_event(device, event) -> int | None:
    """Return brightness delta for a key press, or None if unrelated."""
    if event.type != 1 or event.value != 1:
        return None

    step = int(os.environ.get("GAMEPI_BRIGHTNESS_STEP", "10"))
    _, _, down_names, up_names = brightness_button_names()
    name = device.name.casefold()

    if name in up_names and event.code == BRIGHTNESS_UP:
        return step
    if name in down_names and event.code == BRIGHTNESS_DOWN:
        return -step
    return None


def describe_input_devices() -> list[dict[str, object]]:
    from evdev import InputDevice, list_devices

    devices: list[dict[str, object]] = []
    for path in list_devices():
        device = InputDevice(path)
        keys = sorted(device.capabilities().get(1, []))
        devices.append(
            {
                "path": path,
                "name": device.name,
                "keys": keys,
            }
        )
    return devices


def brightness_input_warnings() -> list[str]:
    devices = describe_input_devices()
    warnings: list[str] = []
    names = {entry["name"] for entry in devices}
    if "button@e" not in names:
        warnings.append(
            "GPR device button@e (GPIO 14, key 225) missing; re-run install-gamepi13-keys.sh and reboot"
        )
    if "button@14" in names:
        warnings.append(
            "button@14 is GPIO 20 / GPB (key 48), not the R shoulder button; do not use it for brightness"
        )
    return warnings
