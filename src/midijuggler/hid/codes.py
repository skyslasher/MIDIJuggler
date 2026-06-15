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


def resolve_evdev_code(name: str) -> tuple[int, int]:
    """Return (event_type, code) for an evdev code name such as BTN_A or ABS_X."""

    _, ecodes = _require_evdev()
    normalized = str(name).strip().upper()
    if not normalized:
        raise ValueError("HID input code must not be empty")

    code = ecodes.ecodes.get(normalized)
    if code is None:
        raise ValueError(f"unknown evdev code: {name!r}")

    for event_type, codes in ecodes.bytype.items():
        if code in codes:
            return int(event_type), int(code)

    raise ValueError(f"could not determine event type for evdev code: {name!r}")


def evdev_code_name(event_type: int, code: int) -> str:
    _, ecodes = _require_evdev()
    for name, value in ecodes.ecodes.items():
        if value == code:
            return name
    return f"type{event_type}_code{code}"


def resolve_device_path(options: dict[str, Any]) -> str:
    device = str(options.get("device", "")).strip()
    if device:
        return device

    vendor_id = options.get("vendor_id")
    product_id = options.get("product_id")
    if vendor_id is None or product_id is None:
        raise ValueError("HID adapter requires device or vendor_id and product_id")

    evdev, _ = _require_evdev()
    vendor = _parse_id(vendor_id, "vendor_id")
    product = _parse_id(product_id, "product_id")

    for path in evdev.list_devices():
        try:
            device_info = evdev.InputDevice(path).info
        except (OSError, PermissionError):
            continue
        if device_info.vendor == vendor and device_info.product == product:
            return path

    raise ValueError(
        f"no HID device found for vendor_id=0x{vendor:04x} product_id=0x{product:04x}"
    )


def _parse_id(value: Any, field_name: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        return int(text, 16) if text.startswith("0x") else int(text)
    raise ValueError(f"HID option {field_name} must be an integer or hex string")
