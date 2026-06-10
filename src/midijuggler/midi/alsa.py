"""Parse ALSA sequencer dump output into MIDI status bytes."""

from __future__ import annotations

import re

ASEQDUMP_LINE = re.compile(
    r"^\s*\d+:\d+\s+(.+?)\s+(\d+)(?:,\s*(.+))?\s*$"
)


def parse_aseqdump_line(line: str) -> tuple[int, tuple[int, ...]] | None:
    """Convert one `aseqdump` line into a MIDI status byte and data bytes."""

    stripped = line.strip()
    if not stripped or stripped.startswith("Waiting for"):
        return None

    match = ASEQDUMP_LINE.match(stripped)
    if not match:
        if stripped.casefold().endswith("clock"):
            return (0xF8, ())
        return None

    event_type = match.group(1).strip().casefold()
    channel = int(match.group(2))
    details = (match.group(3) or "").strip()

    if event_type == "note on":
        note, velocity = _parse_note_velocity(details)
        return (0x90 | channel, (note, velocity))
    if event_type == "note off":
        note, velocity = _parse_note_velocity(details)
        return (0x80 | channel, (note, velocity))
    if event_type == "control change":
        controller, value = _parse_controller_value(details)
        return (0xB0 | channel, (controller, value))
    if event_type == "program change":
        program = _parse_program(details)
        return (0xC0 | channel, (program,))
    if event_type == "pitch bend":
        lsb, msb = _parse_pitch_bend(details)
        return (0xE0 | channel, (lsb, msb))
    if event_type == "channel pressure":
        pressure = _parse_single_value(details, "pressure")
        return (0xD0 | channel, (pressure,))
    if event_type == "polyphonic pressure":
        note, pressure = _parse_note_pressure(details)
        return (0xA0 | channel, (note, pressure))
    if event_type in {"clock", "real time"}:
        return (0xF8, ())
    if event_type == "start":
        return (0xFA, ())
    if event_type == "stop":
        return (0xFC, ())
    if event_type == "continue":
        return (0xFB, ())
    return None


def _parse_note_velocity(details: str) -> tuple[int, int]:
    note = _parse_single_value(details, "note")
    velocity = _parse_single_value(details, "velocity")
    return note, velocity


def _parse_controller_value(details: str) -> tuple[int, int]:
    controller = _parse_single_value(details, "controller")
    value = _parse_single_value(details, "value")
    return controller, value


def _parse_program(details: str) -> int:
    return _parse_single_value(details, "program")


def _parse_pitch_bend(details: str) -> tuple[int, int]:
    value = _parse_single_value(details, "value")
    return value & 0x7F, (value >> 7) & 0x7F


def _parse_note_pressure(details: str) -> tuple[int, int]:
    note = _parse_single_value(details, "note")
    pressure = _parse_single_value(details, "pressure")
    return note, pressure


def _parse_single_value(details: str, key: str) -> int:
    match = re.search(rf"{re.escape(key)}\s+(-?\d+)", details, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"missing {key} in aseqdump details: {details!r}")
    return int(match.group(1))
