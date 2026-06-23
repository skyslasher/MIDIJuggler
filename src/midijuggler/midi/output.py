"""Send raw MIDI bytes to MIDI output ports."""

from __future__ import annotations

import asyncio
import logging
import re

LOGGER = logging.getLogger(__name__)

_SEQUENCER_ADDRESS_PATTERN = re.compile(r"^\d+:\d+$")


def midi_message_bytes(status: int, data: tuple[int, ...]) -> bytes:
    message = bytes([status & 0xFF])
    for byte in data:
        message += bytes([byte & 0x7F])
    return message


def format_amidi_hex(status: int, data: tuple[int, ...]) -> str:
    return " ".join(f"{byte:02x}" for byte in midi_message_bytes(status, data))


def is_sequencer_port_address(port_address: str) -> bool:
    return bool(_SEQUENCER_ADDRESS_PATTERN.match(port_address.strip()))


def format_aseqsend_hex_string(status: int, data: tuple[int, ...]) -> str:
    message_bytes = [status & 0xFF, *[byte & 0x7F for byte in data]]
    return " ".join(f"{byte:02X}" for byte in message_bytes)


def format_aseqsend_args(port_address: str, status: int, data: tuple[int, ...]) -> list[str]:
    return ["aseqsend", "-p", port_address, format_aseqsend_hex_string(status, data)]


async def send_midi_message_to_port(
    port_address: str,
    status: int,
    data: tuple[int, ...],
) -> None:
    if not port_address.strip():
        raise OSError("no MIDI output port configured")

    from midijuggler.midi.mido_io import send_mido_message

    await asyncio.to_thread(send_mido_message, port_address, status, data)
