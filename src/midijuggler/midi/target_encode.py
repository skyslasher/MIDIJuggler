"""Encode MIDI library target parameters into outgoing MIDI messages."""

from __future__ import annotations

from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.midi.library_match import _parameter_matches_port, resolve_library_port
from midijuggler.midi_library import MidiParameter, get_midi_library

NOTE_OFF = 0x80
NOTE_ON = 0x90
CONTROL_CHANGE = 0xB0
PROGRAM_CHANGE = 0xC0
PITCH_BEND = 0xE0


def resolve_midi_target_parameter(
    config: AppConfig,
    adapter_name: str,
    parameter_id: str,
) -> MidiParameter:
    adapter = config.adapters.get(adapter_name)
    if adapter is None:
        raise ValueError(f"unknown MIDI adapter: {adapter_name}")

    library_id = str(adapter.options.get("midi_library", "")).strip()
    if not library_id:
        raise ValueError(f"MIDI adapter {adapter_name} has no midi_library configured")

    library = get_midi_library(library_id)
    library_port = resolve_library_port(adapter)
    matches = [
        parameter
        for parameter in library.parameters
        if parameter.id == parameter_id
        and parameter.direction == "target"
        and _parameter_matches_port(parameter, library_port)
    ]
    if not matches:
        matches = [
            parameter
            for parameter in library.parameters
            if parameter.id == parameter_id and parameter.direction == "target"
        ]
    if not matches:
        raise ValueError(
            f"unknown MIDI parameter {parameter_id!r} in library {library_id!r}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"MIDI parameter {parameter_id!r} is ambiguous for adapter {adapter_name}"
        )
    return matches[0]


def lookup_midi_target_ranges(
    config: AppConfig,
    adapter_name: str,
    parameter_id: str,
) -> tuple[float, float]:
    parameter = resolve_midi_target_parameter(config, adapter_name, parameter_id)
    return float(parameter.value_min), float(parameter.value_max)


def encode_midi_target_message(
    parameter: MidiParameter,
    value: float,
) -> tuple[int, tuple[int, ...]]:
    if parameter.direction != "target":
        raise ValueError(f"MIDI parameter {parameter.id!r} is not a target")
    if parameter.message_type == "sysex":
        raise ValueError(
            f"MIDI parameter {parameter.label!r} uses sysex and cannot be test-sent"
        )
    if parameter.midi_channel is None:
        raise ValueError(f"MIDI parameter {parameter.label!r} is missing midi_channel")

    channel = parameter.midi_channel - 1
    scaled = _scaled_midi_value(parameter, value)

    if parameter.message_type == "control_change":
        if parameter.number is None:
            raise ValueError(f"MIDI parameter {parameter.label!r} is missing controller number")
        return (CONTROL_CHANGE | channel, (parameter.number, scaled))

    if parameter.message_type == "note":
        if parameter.number is None:
            raise ValueError(f"MIDI parameter {parameter.label!r} is missing note number")
        if scaled <= 0:
            return (NOTE_OFF | channel, (parameter.number, 0))
        return (NOTE_ON | channel, (parameter.number, min(127, scaled)))

    if parameter.message_type == "program_change":
        return (PROGRAM_CHANGE | channel, (scaled,))

    if parameter.message_type == "pitch_bend":
        bend = max(0, min(16383, scaled))
        return (PITCH_BEND | channel, (bend & 0x7F, (bend >> 7) & 0x7F))

    raise ValueError(
        f"unsupported MIDI message_type {parameter.message_type!r} for {parameter.label!r}"
    )


def _scaled_midi_value(parameter: MidiParameter, value: float) -> int:
    minimum = float(parameter.value_min)
    maximum = float(parameter.value_max)
    clamped = min(max(float(value), minimum), maximum)
    if parameter.value_type == "int":
        return int(round(clamped))
    return int(round(clamped))


def adapter_has_midi_library(adapter: AdapterConfig | None) -> bool:
    if adapter is None:
        return False
    return bool(str(adapter.options.get("midi_library", "")).strip())
