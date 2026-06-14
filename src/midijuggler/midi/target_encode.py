"""Encode MIDI library target parameters into outgoing MIDI messages."""

from __future__ import annotations

from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.midi.library_match import _parameter_matches_port, resolve_library_port
from midijuggler.midi.xtouch_channels import resolve_parameter_midi_channel
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
    *,
    adapter: AdapterConfig | None = None,
) -> tuple[int, tuple[int, ...]]:
    if parameter.direction != "target":
        raise ValueError(f"MIDI parameter {parameter.id!r} is not a target")
    if parameter.message_type == "sysex":
        raise ValueError(
            f"MIDI parameter {parameter.label!r} uses sysex and cannot be test-sent"
        )
    if parameter.midi_channel is None:
        raise ValueError(f"MIDI parameter {parameter.label!r} is missing midi_channel")

    channel = (
        resolve_parameter_midi_channel(adapter, parameter) - 1
        if adapter is not None
        else parameter.midi_channel - 1
    )
    scaled = _scaled_midi_value(parameter, value)

    if parameter.message_type == "control_change":
        if parameter.number is None:
            raise ValueError(f"MIDI parameter {parameter.label!r} is missing controller number")
        return (CONTROL_CHANGE | channel, (parameter.number, scaled))

    if parameter.message_type == "note":
        if parameter.number is None:
            raise ValueError(f"MIDI parameter {parameter.label!r} is missing note number")
        if scaled <= 0:
            velocity = (
                parameter.note_off_velocity
                if parameter.note_off_velocity is not None
                else 0
            )
            return (NOTE_OFF | channel, (parameter.number, velocity))
        velocity = (
            parameter.note_on_velocity
            if parameter.note_on_velocity is not None
            else min(127, scaled)
        )
        return (NOTE_ON | channel, (parameter.number, min(127, velocity)))

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


def encode_mapped_midi_target(
    config: AppConfig,
    adapter_name: str,
    target_point: str,
    value: float,
) -> tuple[int, tuple[int, ...]]:
    """Encode a mapped MIDI target such as ``cc:1:64`` or a library parameter id."""

    try:
        parameter = resolve_midi_target_parameter(config, adapter_name, target_point)
    except ValueError:
        encoded = encode_legacy_midi_target_point(target_point, value)
        if encoded is None:
            raise ValueError(f"unsupported MIDI target point {target_point!r}")
        return encoded
    adapter = config.adapters.get(adapter_name)
    return encode_midi_target_message(parameter, value, adapter=adapter)


def encode_legacy_midi_target_point(
    point: str,
    value: float,
) -> tuple[int, tuple[int, ...]] | None:
    """Encode raw MIDI target notation used by mappings and data points."""

    if point.startswith("cc:"):
        parts = point.split(":")
        if len(parts) != 3:
            return None
        channel = int(parts[1]) - 1
        controller = int(parts[2])
        scaled = max(0, min(127, int(round(value))))
        return (CONTROL_CHANGE | (channel & 0x0F), (controller, scaled))

    if point.startswith("note:"):
        parts = point.split(":")
        if len(parts) != 3:
            return None
        channel = int(parts[1]) - 1
        note = int(parts[2])
        scaled = max(0, min(127, int(round(value))))
        if scaled <= 0:
            return (NOTE_OFF | (channel & 0x0F), (note, 0))
        return (NOTE_ON | (channel & 0x0F), (note, scaled))

    if point.startswith("program:"):
        parts = point.split(":")
        if len(parts) != 3:
            return None
        channel = int(parts[1]) - 1
        program = max(0, min(127, int(round(value))))
        return (PROGRAM_CHANGE | (channel & 0x0F), (program,))

    if point.startswith("pitch_bend:"):
        parts = point.split(":")
        if len(parts) != 2:
            return None
        channel = int(parts[1]) - 1
        bend = max(0, min(16383, int(round(value))))
        return (PITCH_BEND | (channel & 0x0F), (bend & 0x7F, (bend >> 7) & 0x7F))

    if point.startswith("cc_"):
        parts = point.split("_")
        if len(parts) != 3:
            return None
        channel = max(0, int(parts[1]) - 1)
        controller = int(parts[2])
        scaled = max(0, min(127, int(round(value))))
        return (CONTROL_CHANGE | (channel & 0x0F), (controller, scaled))

    if point.startswith("note_"):
        parts = point.split("_")
        if len(parts) != 3:
            return None
        channel = max(0, int(parts[1]) - 1)
        note = int(parts[2])
        scaled = max(0, min(127, int(round(value))))
        if scaled <= 0:
            return (NOTE_OFF | (channel & 0x0F), (note, 0))
        return (NOTE_ON | (channel & 0x0F), (note, scaled))

    if point.startswith("program_"):
        parts = point.split("_")
        if len(parts) != 3:
            return None
        channel = max(0, int(parts[1]) - 1)
        program = max(0, min(127, int(round(value))))
        return (PROGRAM_CHANGE | (channel & 0x0F), (program,))

    if point.startswith("pitch_bend_"):
        channel_text = point.removeprefix("pitch_bend_")
        if not channel_text.isdigit():
            return None
        channel = max(0, int(channel_text) - 1)
        bend = max(0, min(16383, int(round(value))))
        return (PITCH_BEND | (channel & 0x0F), (bend & 0x7F, (bend >> 7) & 0x7F))

    return None
