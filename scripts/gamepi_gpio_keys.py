"""Find GamePi13 gpio-key input devices (per-GPIO button@XX or legacy gpio-keys)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

START_CODE = 31  # KEY_S
BRIGHTNESS_DOWN = 224
BRIGHTNESS_UP = 225

GPR_GPIO = 14
UART_GPIO_LINES = (14, 15)

_BOOT_CONFIG_CANDIDATES = (
    Path("/boot/firmware/config.txt"),
    Path("/boot/config.txt"),
)
_CMDLINE_CANDIDATES = (
    Path("/boot/firmware/cmdline.txt"),
    Path("/boot/cmdline.txt"),
)


def gpio_button_name(gpio: int) -> str:
    """Kernel names per-GPIO buttons with the GPIO number in hex: GPIO 14 -> button@e."""
    return f"button@{gpio:x}"


def _env_gpio(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def resolve_boot_config() -> Path | None:
    override = os.environ.get("GAMEPI_BOOT_CONFIG", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    for path in _BOOT_CONFIG_CANDIDATES:
        if path.is_file():
            return path
    return None


def resolve_cmdline() -> Path | None:
    override = os.environ.get("GAMEPI_BOOT_CMDLINE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    for path in _CMDLINE_CANDIDATES:
        if path.is_file():
            return path
    return None


def _read_text_lines(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _strip_comment(line: str) -> str:
    if "#" in line:
        return line.split("#", 1)[0].strip()
    return line.strip()


def _truthy_boot_value(raw: str) -> bool:
    return raw.strip().lower() in {"1", "on", "true", "yes"}


def _falsy_boot_value(raw: str) -> bool:
    return raw.strip().lower() in {"0", "off", "false", "no"}


def boot_config_uart_reserves_gpio_14(lines: list[str] | None = None) -> bool:
    """Return True when boot config likely assigns GPIO 14 to UART (blocks GPR gpio-key)."""
    if lines is None:
        lines = _read_text_lines(resolve_boot_config())

    uart_enabled = False
    for raw in lines:
        line = _strip_comment(raw)
        if not line:
            continue
        if line.startswith("enable_uart="):
            value = line.split("=", 1)[1]
            if _truthy_boot_value(value):
                uart_enabled = True
            if _falsy_boot_value(value):
                uart_enabled = False
            continue
        if line.startswith("dtparam=") and "uart" in line.casefold():
            if re.search(r"uart0=(on|1|true|yes)", line, re.I):
                uart_enabled = True
            if re.search(r"uart0=(off|0|false|no)", line, re.I):
                uart_enabled = False
        if line.startswith("dtoverlay=") and re.search(
            r"dtoverlay=(uart0|miniuart-bt|pi3-miniuart-bt)\b", line, re.I
        ):
            uart_enabled = True
    return uart_enabled


def cmdline_serial_console(lines: list[str] | None = None) -> bool:
    if lines is None:
        lines = _read_text_lines(resolve_cmdline())
    if not lines:
        return False
    text = " ".join(line.strip() for line in lines if line.strip())
    return bool(
        re.search(r"\bconsole=(serial0|ttyAMA0|ttyS0)\b", text)
        or re.search(r"\bconsole=.*,115200\b", text)
    )


def boot_config_gpio_conflicts(gpio: int, lines: list[str] | None = None) -> list[str]:
    """Return human-readable warnings for config lines that claim the same BCM GPIO."""
    if lines is None:
        lines = _read_text_lines(resolve_boot_config())

    conflicts: list[str] = []
    gpio_pattern = re.compile(rf"\bgpio={gpio}\b")
    for raw in lines:
        line = _strip_comment(raw)
        if not line or not gpio_pattern.search(line):
            continue
        if line.startswith("dtoverlay=gpio-key,"):
            continue
        conflicts.append(line)
    return conflicts


def boot_config_overlay_line(label: str, lines: list[str] | None = None) -> str | None:
    if lines is None:
        lines = _read_text_lines(resolve_boot_config())
    pattern = re.compile(rf'label="{re.escape(label)}"')
    for raw in lines:
        line = _strip_comment(raw)
        if line.startswith("dtoverlay=gpio-key,") and pattern.search(line):
            return line
    return None


def boot_config_warnings() -> list[str]:
    """Warnings from boot config / cmdline that explain missing gpio-key devices."""
    boot_config = resolve_boot_config()
    lines = _read_text_lines(boot_config)
    warnings: list[str] = []

    if boot_config is None:
        warnings.append("boot config not found (set GAMEPI_BOOT_CONFIG)")
        return warnings

    gpr_line = boot_config_overlay_line("GPR", lines)
    r_gpio = _env_gpio("GAMEPI_R_GPIO", GPR_GPIO)
    expected_name = gpio_button_name(r_gpio)

    if gpr_line is None:
        warnings.append(
            f'GPR overlay missing in {boot_config}; run install-gamepi13-keys.sh'
        )
    elif not re.search(rf"\bgpio={r_gpio}\b", gpr_line):
        warnings.append(
            f'GPR overlay in {boot_config} does not use gpio={r_gpio}: {gpr_line}'
        )

    if r_gpio == GPR_GPIO and boot_config_uart_reserves_gpio_14(lines):
        warnings.append(
            "enable_uart=1 (or uart0 overlay) reserves GPIO 14 (UART TX) — "
            "gpio-key GPR cannot register button@e; set enable_uart=0 and remove "
            "console=serial0 from cmdline.txt, then reboot"
        )

    if r_gpio == GPR_GPIO and cmdline_serial_console():
        warnings.append(
            "cmdline.txt uses a serial console (console=serial0/ttyAMA0) on GPIO 14/15 — "
            "disable it for GPR / button@e"
        )

    for conflict in boot_config_gpio_conflicts(r_gpio, lines):
        if "mk_arcade_joystick" in conflict or "joy" in conflict.casefold():
            warnings.append(f"another overlay claims GPIO {r_gpio}: {conflict}")

    return warnings


def brightness_backend_warnings() -> list[str]:
    """Explain why hardware backlight sysfs/PWM may be unavailable on GamePi13."""
    lines = _read_text_lines(resolve_boot_config())
    warnings: list[str] = []
    if re.search(r"dtoverlay=waveshare13\b", "\n".join(lines)):
        warnings.append(
            "waveshare13 owns GPIO 24 for panel backlight — expect no panel entry under "
            "/sys/class/leds and 'GPIO busy' if userspace PWM is enabled on GPIO 24"
        )
        warnings.append(
            "MIDIJuggler software brightness stores level 0–255 and dims the kiosk UI "
            "(CSS filter); xgamma/xrandr on fb0 often has no visible effect on GamePi13"
        )
    return warnings


def dmesg_gpio_key_hints(gpio: int = GPR_GPIO) -> list[str]:
    """Best-effort dmesg lines about gpio-key probe failures (requires readable dmesg)."""
    try:
        result = subprocess.run(
            ["dmesg", "--color=never"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    hints: list[str] = []
    patterns = (
        re.compile(rf"gpio.?{gpio}\b", re.I),
        re.compile(r"gpio-key", re.I),
        re.compile(r"gpiokeys", re.I),
    )
    for line in result.stdout.splitlines():
        if not any(pattern.search(line) for pattern in patterns):
            continue
        lowered = line.casefold()
        if any(token in lowered for token in ("fail", "error", "busy", "unable", "could not")):
            hints.append(line.strip())
    return hints[-5:]


def brightness_button_names() -> tuple[str, str, set[str], set[str]]:
    l_gpio = _env_gpio("GAMEPI_L_GPIO", 23)
    r_gpio = _env_gpio("GAMEPI_R_GPIO", GPR_GPIO)
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
    _, expected_up, _, _ = brightness_button_names()
    devices = describe_input_devices()
    warnings: list[str] = []
    names = {str(entry["name"]) for entry in devices}

    if expected_up not in names and "gpr" not in {name.casefold() for name in names}:
        warnings.append(
            f"GPR device {expected_up} (GPIO {_env_gpio('GAMEPI_R_GPIO', GPR_GPIO)}, "
            f"key {BRIGHTNESS_UP}) missing; check boot overlays and reboot"
        )
        warnings.extend(boot_config_warnings())
        hints = dmesg_gpio_key_hints(_env_gpio("GAMEPI_R_GPIO", GPR_GPIO))
        for hint in hints:
            warnings.append(f"dmesg: {hint}")

    if "button@14" in names:
        warnings.append(
            "button@14 is GPIO 20 / GPB (key 48), not the R shoulder button; do not use it for brightness"
        )
    return warnings


def verify_keys_ok() -> bool:
    """Return True when expected shoulder evdev devices are present."""
    warnings = brightness_input_warnings()
    return not any("missing" in warning.casefold() for warning in warnings)
