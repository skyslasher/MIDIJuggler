"""Configurable MIDI channels for the Behringer X-Touch Mini."""

from __future__ import annotations

from midijuggler.config import AdapterConfig
from midijuggler.midi_library import MidiParameter

XTOUCH_MINI_LIBRARY_ID = "behringer_xtouch_mini"
DEFAULT_XTOUCH_VALUE_CHANNEL = 11
DEFAULT_XTOUCH_DISPLAY_CHANNEL = 12


def uses_xtouch_library(config: AdapterConfig) -> bool:
    library_id = str(config.options.get("midi_library", "")).strip()
    return library_id == XTOUCH_MINI_LIBRARY_ID


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


def xtouch_value_channel(config: AdapterConfig) -> int:
    return parse_midi_channel_option(
        config.options.get("midi_value_channel"),
        field_name="midi_value_channel",
        default=DEFAULT_XTOUCH_VALUE_CHANNEL,
    )


def xtouch_display_channel(config: AdapterConfig) -> int:
    return parse_midi_channel_option(
        config.options.get("midi_display_channel"),
        field_name="midi_display_channel",
        default=DEFAULT_XTOUCH_DISPLAY_CHANNEL,
    )


def is_led_ring_display_parameter(parameter: MidiParameter) -> bool:
    return parameter.category == "feedback" and parameter.id.endswith("_led_ring")


def resolve_parameter_midi_channel(
    adapter: AdapterConfig,
    parameter: MidiParameter,
) -> int:
    if parameter.midi_channel is None:
        raise ValueError(f"MIDI parameter {parameter.label!r} is missing midi_channel")
    if not uses_xtouch_library(adapter):
        return parameter.midi_channel
    if is_led_ring_display_parameter(parameter):
        return xtouch_display_channel(adapter)
    return xtouch_value_channel(adapter)
