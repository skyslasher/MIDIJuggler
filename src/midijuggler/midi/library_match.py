"""Match raw MIDI messages against packaged controller libraries."""

from __future__ import annotations

from dataclasses import dataclass

from midijuggler.config import AdapterConfig
from midijuggler.device.types import DeviceConfig
from midijuggler.midi.xtouch_channels import resolve_parameter_midi_channel
from midijuggler.midi_library import MidiLibrary, MidiParameter

NOTE_OFF = 0x80
NOTE_ON = 0x90
CONTROL_CHANGE = 0xB0
PROGRAM_CHANGE = 0xC0
PITCH_BEND = 0xE0


@dataclass(frozen=True)
class MatchedControl:
    """One library control resolved from an incoming MIDI message."""

    control_id: str
    value: float


@dataclass
class MidiSourceIndex:
    """Lookup table for source-direction parameters in one MIDI library."""

    _by_note: dict[tuple[int, int], list[MidiParameter]]
    _by_control_change: dict[tuple[int, int], list[MidiParameter]]
    _by_program_change: dict[tuple[int, int], list[MidiParameter]]
    _by_pitch_bend: dict[int, list[MidiParameter]]
    _by_note_number: dict[int, list[MidiParameter]]
    _by_cc_number: dict[int, list[MidiParameter]]

    def match(self, status: int, data: tuple[int, ...]) -> list[MatchedControl]:
        message_type = status & 0xF0
        channel = status & 0x0F

        if message_type == NOTE_ON:
            return self._match_note(channel, data, pressed=data[1] > 0)
        if message_type == NOTE_OFF:
            return self._match_note(channel, data, pressed=False)
        if message_type == CONTROL_CHANGE and len(data) >= 2:
            return self._match_control_change(channel, data[0], float(data[1]))
        if message_type == PROGRAM_CHANGE and data:
            return self._match_program_change(channel, data[0], float(data[0]))
        if message_type == PITCH_BEND and len(data) >= 2:
            value = float(data[0] + (data[1] << 7))
            return self._match_pitch_bend(channel, value)
        return []

    def match_relaxed(self, status: int, data: tuple[int, ...]) -> list[MatchedControl]:
        """Match ignoring MIDI channel when the library entry is unambiguous."""

        exact = self.match(status, data)
        if exact:
            return exact

        message_type = status & 0xF0
        if message_type in {NOTE_ON, NOTE_OFF} and data:
            pressed = message_type == NOTE_ON and len(data) > 1 and data[1] > 0
            value = float(data[1]) if pressed and len(data) > 1 else 0.0
            return self._match_unique_note_number(data[0], value)
        if message_type == CONTROL_CHANGE and len(data) >= 2:
            return self._match_unique_cc_number(data[0], float(data[1]))
        return []

    def _match_note(
        self,
        channel: int,
        data: tuple[int, ...],
        *,
        pressed: bool,
    ) -> list[MatchedControl]:
        if not data:
            return []
        parameters = self._by_note.get((channel, data[0]), [])
        value = float(data[1]) if pressed and len(data) > 1 else 0.0
        return [
            MatchedControl(control_id=parameter.id, value=value)
            for parameter in parameters
        ]

    def _match_control_change(
        self,
        channel: int,
        controller: int,
        value: float,
    ) -> list[MatchedControl]:
        parameters = self._by_control_change.get((channel, controller), [])
        return [
            MatchedControl(control_id=parameter.id, value=value)
            for parameter in parameters
        ]

    def _match_program_change(
        self,
        channel: int,
        program: int,
        value: float,
    ) -> list[MatchedControl]:
        parameters = self._by_program_change.get((channel, program), [])
        return [
            MatchedControl(control_id=parameter.id, value=value)
            for parameter in parameters
        ]

    def _match_pitch_bend(self, channel: int, value: float) -> list[MatchedControl]:
        parameters = self._by_pitch_bend.get(channel, [])
        return [
            MatchedControl(control_id=parameter.id, value=value)
            for parameter in parameters
        ]

    def _match_unique_cc_number(
        self,
        controller: int,
        value: float,
    ) -> list[MatchedControl]:
        parameters = self._by_cc_number.get(controller, [])
        if len(parameters) != 1:
            return []
        return [MatchedControl(control_id=parameters[0].id, value=value)]

    def _match_unique_note_number(
        self,
        note: int,
        value: float,
    ) -> list[MatchedControl]:
        parameters = self._by_note_number.get(note, [])
        if len(parameters) != 1:
            return []
        return [MatchedControl(control_id=parameters[0].id, value=value)]


def resolve_incoming_controls(
    index: MidiSourceIndex | None,
    status: int,
    data: tuple[int, ...],
) -> list[MatchedControl]:
    """Resolve library and raw MIDI controls for one incoming message."""

    if index is not None:
        matches = index.match_relaxed(status, data)
        if matches:
            return matches

    raw_control = format_raw_midi_control(status, data)
    if raw_control is None:
        return []
    return [MatchedControl(control_id=raw_control, value=extract_midi_value(status, data))]


def format_raw_midi_control(status: int, data: tuple[int, ...]) -> str | None:
    message_type = status & 0xF0
    channel = status & 0x0F

    if message_type == CONTROL_CHANGE and len(data) >= 2:
        return f"cc_{channel}_{data[0]}"
    if message_type in {NOTE_ON, NOTE_OFF} and data:
        return f"note_{channel}_{data[0]}"
    if message_type == PITCH_BEND and len(data) >= 2:
        return f"pitch_bend_{channel}"
    if message_type == PROGRAM_CHANGE and data:
        return f"program_{channel}_{data[0]}"
    return None


def extract_midi_value(status: int, data: tuple[int, ...]) -> float:
    message_type = status & 0xF0
    if message_type in {NOTE_ON, NOTE_OFF} and data:
        if message_type == NOTE_OFF or (len(data) > 1 and data[1] == 0):
            return 0.0
        return float(data[1]) if len(data) > 1 else 0.0
    if message_type == CONTROL_CHANGE and len(data) >= 2:
        return float(data[1])
    if message_type == PITCH_BEND and len(data) >= 2:
        return float(data[0] + (data[1] << 7))
    if message_type == PROGRAM_CHANGE and data:
        return float(data[0])
    return 0.0


def build_source_index(
    library: MidiLibrary,
    library_port: str | None = None,
    *,
    adapter: AdapterConfig | None = None,
    device: DeviceConfig | None = None,
) -> MidiSourceIndex:
    """Index all source parameters for fast MIDI message matching."""

    by_note: dict[tuple[int, int], list[MidiParameter]] = {}
    by_control_change: dict[tuple[int, int], list[MidiParameter]] = {}
    by_program_change: dict[tuple[int, int], list[MidiParameter]] = {}
    by_pitch_bend: dict[int, list[MidiParameter]] = {}
    by_note_number: dict[int, list[MidiParameter]] = {}
    by_cc_number: dict[int, list[MidiParameter]] = {}

    for parameter in library.parameters:
        if parameter.direction != "source":
            continue
        if not _parameter_matches_port(parameter, library_port):
            continue
        if parameter.midi_channel is None:
            continue

        channel = (
            resolve_parameter_midi_channel(adapter, parameter, device=device) - 1
            if adapter is not None
            else parameter.midi_channel - 1
        )
        if parameter.message_type == "note":
            if parameter.number is None:
                continue
            _append(by_note, (channel, parameter.number), parameter)
            _append(by_note_number, parameter.number, parameter)
        elif parameter.message_type == "control_change":
            if parameter.number is None:
                continue
            _append(by_control_change, (channel, parameter.number), parameter)
            _append(by_cc_number, parameter.number, parameter)
        elif parameter.message_type == "program_change":
            if parameter.number is None:
                continue
            _append(by_program_change, (channel, parameter.number), parameter)
        elif parameter.message_type == "pitch_bend":
            _append(by_pitch_bend, channel, parameter)
        else:
            continue

    return MidiSourceIndex(
        _by_note=by_note,
        _by_control_change=by_control_change,
        _by_program_change=by_program_change,
        _by_pitch_bend=by_pitch_bend,
        _by_note_number=by_note_number,
        _by_cc_number=by_cc_number,
    )


def resolve_library_port(config: AdapterConfig) -> str | None:
    """Resolve the logical library port filter for a MIDI adapter instance."""

    explicit = str(config.options.get("midi_port", "")).strip()
    if explicit:
        return explicit

    input_port = str(config.options.get("input_port", "")).strip().casefold()
    if "port 2" in input_port or "port_2" in input_port:
        return "port_2"
    if "port 1" in input_port or "port_1" in input_port:
        return "port_1"
    return None


def _parameter_matches_port(parameter: MidiParameter, library_port: str | None) -> bool:
    if library_port is None:
        return parameter.port == ""
    return parameter.port == library_port


def _append(mapping: dict, key, parameter: MidiParameter) -> None:
    mapping.setdefault(key, []).append(parameter)
