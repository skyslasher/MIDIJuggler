"""Configurable MIDI channels for Behringer X-Touch controllers."""

from __future__ import annotations

from dataclasses import dataclass

from midijuggler.config import AdapterConfig
from midijuggler.device.types import DeviceConfig
from midijuggler.midi_library import MidiParameter

XTOUCH_MINI_LIBRARY_ID = "behringer_xtouch_mini"
XTOUCH_COMPACT_LIBRARY_ID = "behringer_xtouch_compact"
XTOUCH_LIBRARY_IDS = frozenset({XTOUCH_MINI_LIBRARY_ID, XTOUCH_COMPACT_LIBRARY_ID})

DEFAULT_XTOUCH_MINI_VALUE_CHANNEL = 11
DEFAULT_XTOUCH_MINI_DISPLAY_CHANNEL = 12
DEFAULT_XTOUCH_COMPACT_VALUE_CHANNEL = 1
DEFAULT_XTOUCH_COMPACT_DISPLAY_CHANNEL = 1

# Backwards-compatible aliases for the Mini defaults.
DEFAULT_XTOUCH_VALUE_CHANNEL = DEFAULT_XTOUCH_MINI_VALUE_CHANNEL
DEFAULT_XTOUCH_DISPLAY_CHANNEL = DEFAULT_XTOUCH_MINI_DISPLAY_CHANNEL


def is_xtouch_library(library_id: str) -> bool:
    return library_id in XTOUCH_LIBRARY_IDS


def default_xtouch_value_channel(library_id: str) -> int:
    if library_id == XTOUCH_COMPACT_LIBRARY_ID:
        return DEFAULT_XTOUCH_COMPACT_VALUE_CHANNEL
    return DEFAULT_XTOUCH_MINI_VALUE_CHANNEL


def default_xtouch_display_channel(library_id: str) -> int:
    if library_id == XTOUCH_COMPACT_LIBRARY_ID:
        return DEFAULT_XTOUCH_COMPACT_DISPLAY_CHANNEL
    return DEFAULT_XTOUCH_MINI_DISPLAY_CHANNEL


@dataclass(frozen=True)
class XTouchDeviceOptions:
    library_id: str
    feedback_refresh_interval: float
    midi_value_channel: int
    midi_display_channel: int


def xtouch_device_options(
    adapter: AdapterConfig,
    device: DeviceConfig | None = None,
    *,
    library_id: str | None = None,
) -> XTouchDeviceOptions:
    resolved_library = (
        str(library_id or "").strip()
        or (device.library.strip() if device is not None else "")
        or str(adapter.options.get("midi_library", "")).strip()
    )
    interval = 0.0
    if device is not None and device.feedback_refresh_interval > 0:
        interval = device.feedback_refresh_interval
    else:
        raw_interval = adapter.options.get("feedback_refresh_interval", 0)
        try:
            interval = max(0.0, float(raw_interval))
        except (TypeError, ValueError):
            interval = 0.0

    default_value = default_xtouch_value_channel(resolved_library)
    default_display = default_xtouch_display_channel(resolved_library)
    if device is not None and is_xtouch_library(resolved_library):
        value_channel = device.midi_value_channel
        display_channel = device.midi_display_channel
    else:
        value_channel = parse_midi_channel_option(
            adapter.options.get("midi_value_channel"),
            field_name="midi_value_channel",
            default=default_value,
        )
        display_channel = parse_midi_channel_option(
            adapter.options.get("midi_display_channel"),
            field_name="midi_display_channel",
            default=default_display,
        )

    return XTouchDeviceOptions(
        library_id=resolved_library,
        feedback_refresh_interval=interval,
        midi_value_channel=value_channel,
        midi_display_channel=display_channel,
    )


def uses_xtouch_library(
    adapter: AdapterConfig,
    device: DeviceConfig | None = None,
    *,
    library_id: str | None = None,
) -> bool:
    return is_xtouch_library(
        xtouch_device_options(adapter, device, library_id=library_id).library_id
    )


def parse_midi_channel_option(
    value: object,
    *,
    field_name: str,
    default: int,
) -> int:
    if value is None or value == "":
        return default
    try:
        channel = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer between 1 and 16") from exc
    if not 1 <= channel <= 16:
        raise ValueError(f"{field_name} must be between 1 and 16")
    return channel


def xtouch_value_channel(
    adapter: AdapterConfig,
    device: DeviceConfig | None = None,
) -> int:
    return xtouch_device_options(adapter, device).midi_value_channel


def xtouch_display_channel(
    adapter: AdapterConfig,
    device: DeviceConfig | None = None,
) -> int:
    return xtouch_device_options(adapter, device).midi_display_channel


def is_led_ring_display_parameter(parameter: MidiParameter) -> bool:
    return parameter.category == "feedback" and parameter.id.endswith("_led_ring")


def resolve_parameter_midi_channel(
    adapter: AdapterConfig,
    parameter: MidiParameter,
    *,
    device: DeviceConfig | None = None,
) -> int:
    if parameter.midi_channel is None:
        raise ValueError(f"MIDI parameter {parameter.label!r} is missing midi_channel")
    if not uses_xtouch_library(adapter, device):
        return parameter.midi_channel
    if is_led_ring_display_parameter(parameter):
        return xtouch_display_channel(adapter, device)
    return xtouch_value_channel(adapter, device)
