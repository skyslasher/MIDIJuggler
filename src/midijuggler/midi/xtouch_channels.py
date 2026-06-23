"""Configurable MIDI channels for the Behringer X-Touch Mini."""

from __future__ import annotations

from dataclasses import dataclass

from midijuggler.config import AdapterConfig
from midijuggler.device.types import DeviceConfig
from midijuggler.midi_library import MidiParameter

XTOUCH_MINI_LIBRARY_ID = "behringer_xtouch_mini"
DEFAULT_XTOUCH_VALUE_CHANNEL = 11
DEFAULT_XTOUCH_DISPLAY_CHANNEL = 12


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

    if device is not None and resolved_library == XTOUCH_MINI_LIBRARY_ID:
        value_channel = device.midi_value_channel
        display_channel = device.midi_display_channel
    else:
        value_channel = parse_midi_channel_option(
            adapter.options.get("midi_value_channel"),
            field_name="midi_value_channel",
            default=DEFAULT_XTOUCH_VALUE_CHANNEL,
        )
        display_channel = parse_midi_channel_option(
            adapter.options.get("midi_display_channel"),
            field_name="midi_display_channel",
            default=DEFAULT_XTOUCH_DISPLAY_CHANNEL,
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
    return (
        xtouch_device_options(adapter, device, library_id=library_id).library_id
        == XTOUCH_MINI_LIBRARY_ID
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
