"""Resolve Linux evdev code names for HID input mapping."""

from __future__ import annotations

from typing import Any


def _require_evdev():
    try:
        import evdev
        from evdev import ecodes
    except ImportError as exc:
        raise ImportError(
            "evdev is required for HID adapters. Install with: pip install 'midijuggler[hid]'"
        ) from exc
    return evdev, ecodes


_KEY_CODE_ALIASES = {
    "ENTER": "KEY_ENTER",
    "RETURN": "KEY_ENTER",
    "SPACE": "KEY_SPACE",
    "ESC": "KEY_ESC",
    "ESCAPE": "KEY_ESC",
    "BACKSPACE": "KEY_BACKSPACE",
    "DELETE": "KEY_DELETE",
    "TAB": "KEY_TAB",
}


def normalize_evdev_code_name(name: str) -> str:
    """Normalize user-facing code names to evdev constants."""

    normalized = str(name).strip().upper()
    if not normalized:
        raise ValueError("HID input code must not be empty")

    if normalized in _KEY_CODE_ALIASES:
        return _KEY_CODE_ALIASES[normalized]

    if len(normalized) == 1 and normalized.isalnum():
        return f"KEY_{normalized}"

    if normalized.startswith(("KEY_", "BTN_", "ABS_", "REL_", "SW_", "MSC_", "LED_")):
        return normalized

    try:
        _, ecodes = _require_evdev()
    except ImportError:
        return normalized

    prefixed = f"KEY_{normalized}"
    if ecodes.ecodes.get(prefixed) is not None:
        return prefixed
    return normalized


def keyboard_code_name(event_type: int, code: int) -> str | None:
    """Return the evdev name for a keyboard KEY_* press, if applicable."""

    name = evdev_code_name(event_type, code)
    if name.startswith("KEY_"):
        return name
    return None


def is_keyboard_key(event_type: int, code: int) -> bool:
    """Return True when an EV_KEY code represents a keyboard key."""

    return keyboard_code_name(event_type, code) is not None


def resolve_evdev_code(name: str) -> tuple[int, int]:
    """Return (event_type, code) for an evdev code name such as BTN_A or ABS_X."""

    _, ecodes = _require_evdev()
    normalized = normalize_evdev_code_name(name)

    code = ecodes.ecodes.get(normalized)
    if code is None:
        raise ValueError(f"unknown evdev code: {name!r}")

    for event_type, codes in ecodes.bytype.items():
        if code in codes:
            return int(event_type), int(code)

    raise ValueError(f"could not determine event type for evdev code: {name!r}")


def evdev_code_name(event_type: int, code: int) -> str:
    try:
        _, ecodes = _require_evdev()
    except ImportError:
        return f"type{event_type}_code{code}"

    names = ecodes.bytype.get(int(event_type), {}).get(int(code))
    if names is None:
        return f"type{event_type}_code{code}"
    if isinstance(names, list):
        for name in names:
            normalized = str(name)
            if normalized.startswith("KEY_"):
                return normalized
        return str(names[0])
    return str(names)


def list_input_devices() -> list[dict[str, Any]]:
    """Return readable metadata for available evdev input device nodes."""

    try:
        evdev, _ = _require_evdev()
    except ImportError:
        return []

    devices: list[dict[str, Any]] = []
    for path in sorted(evdev.list_devices()):
        try:
            device = evdev.InputDevice(path)
            info = device.info
            devices.append(
                {
                    "path": path,
                    "name": device.name,
                    "vendor_id": f"0x{info.vendor:04x}",
                    "product_id": f"0x{info.product:04x}",
                }
            )
            device.close()
        except (OSError, PermissionError):
            continue
    return devices


def hid_available() -> bool:
    try:
        _require_evdev()
    except ImportError:
        return False
    return True


def hid_device_key(vendor_id: Any, product_id: Any) -> str:
    """Return a stable select/list key for a HID device identity."""

    vendor = _parse_id(vendor_id, "vendor_id")
    product = _parse_id(product_id, "product_id")
    return f"0x{vendor:04x}:0x{product:04x}"


def parse_hid_device_key(key: str) -> tuple[str, str]:
    """Parse a :-separated vendor/product key into normalized hex strings."""

    parts = str(key).strip().split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"invalid HID device key: {key!r}")
    vendor = _parse_id(parts[0], "vendor_id")
    product = _parse_id(parts[1], "product_id")
    return f"0x{vendor:04x}", f"0x{product:04x}"


def lookup_input_device(
    *,
    vendor_id: Any = None,
    product_id: Any = None,
    device_path: str | None = None,
    devices: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Find a listed input device by USB IDs or by current event node path."""

    listed = list_input_devices() if devices is None else devices
    if vendor_id not in (None, "") and product_id not in (None, ""):
        vendor = _parse_id(vendor_id, "vendor_id")
        product = _parse_id(product_id, "product_id")
        for device in listed:
            if (
                _parse_id(device["vendor_id"], "vendor_id") == vendor
                and _parse_id(device["product_id"], "product_id") == product
            ):
                return device
    if device_path:
        path = str(device_path).strip()
        for device in listed:
            if device["path"] == path:
                return device
    return None


def normalize_hid_device_options(options: dict[str, Any]) -> dict[str, Any]:
    """Prefer vendor/product IDs and migrate legacy device paths when possible."""

    normalized = dict(options)
    vendor_id = normalized.get("vendor_id")
    product_id = normalized.get("product_id")
    device = str(normalized.get("device", "")).strip()

    if (vendor_id in (None, "") or product_id in (None, "")) and device:
        matched = lookup_input_device(device_path=device)
        if matched is not None:
            vendor_id = matched["vendor_id"]
            product_id = matched["product_id"]

    if vendor_id not in (None, "") and product_id not in (None, ""):
        normalized["vendor_id"] = str(vendor_id)
        normalized["product_id"] = str(product_id)
        normalized.pop("device", None)
        return normalized

    if device:
        normalized["device"] = device
    return normalized


def resolve_device_path(options: dict[str, Any]) -> str:
    vendor_id = options.get("vendor_id")
    product_id = options.get("product_id")
    if vendor_id not in (None, "") and product_id not in (None, ""):
        matched = lookup_input_device(vendor_id=vendor_id, product_id=product_id)
        if matched is not None:
            return matched["path"]
        vendor = _parse_id(vendor_id, "vendor_id")
        product = _parse_id(product_id, "product_id")
        raise ValueError(
            f"no HID device found for vendor_id=0x{vendor:04x} product_id=0x{product:04x}"
        )

    device = str(options.get("device", "")).strip()
    if device:
        return device

    raise ValueError("HID adapter requires device or vendor_id and product_id")


def _parse_id(value: Any, field_name: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text.startswith("0x"):
            return int(text, 16)
        if text and all(ch in "0123456789abcdef" for ch in text):
            return int(text, 16)
        return int(text)
    raise ValueError(f"HID option {field_name} must be an integer or hex string")
