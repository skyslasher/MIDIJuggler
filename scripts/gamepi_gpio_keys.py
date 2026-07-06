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


def brightness_button_names() -> tuple[str, str, set[str], set[str]]:
    l_gpio = _env_gpio("GAMEPI_L_GPIO", 23)
    r_gpio = _env_gpio("GAMEPI_R_GPIO", 14)
    l_name = gpio_button_name(l_gpio).casefold()
    r_name = gpio_button_name(r_gpio).casefold()
    down_names = {l_name, "gpl", "gp l"}
    up_names = {r_name, "gpr", "gp r"}
    for label in os.environ.get("GAMEPI_L_LABELS", "GPL").split(","):
        if label.strip():
            down_names.add(label.strip().casefold())
    for label in os.environ.get("GAMEPI_R_LABELS", "GPR").split(","):
        if label.strip():
            up_names.add(label.strip().casefold())
    return l_name, r_name, down_names, up_names


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
        if name in down_names or name in up_names:
            if path not in seen:
                matched.append(device)
                seen.add(path)
            continue
        keys = set(device.capabilities().get(ecodes.EV_KEY, []))
        brightness_keys = keys & {BRIGHTNESS_DOWN, BRIGHTNESS_UP}
        if not brightness_keys:
            continue
        meta_keys = {0}
        if keys - brightness_keys - meta_keys:
            continue
        if path not in seen:
            matched.append(device)
            seen.add(path)

    if legacy is not None:
        keys = legacy.capabilities().get(ecodes.EV_KEY, [])
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

    if name in up_names:
        return step
    if name in down_names:
        return -step
    if event.code == BRIGHTNESS_UP:
        return step
    if event.code == BRIGHTNESS_DOWN:
        return -step
    return None
