"""Send raw MIDI bytes to ALSA sequencer ports."""

from __future__ import annotations

import asyncio
import logging
import shutil

LOGGER = logging.getLogger(__name__)


def midi_message_bytes(status: int, data: tuple[int, ...]) -> bytes:
    message = bytes([status & 0xFF])
    for byte in data:
        message += bytes([byte & 0x7F])
    return message


def format_amidi_hex(status: int, data: tuple[int, ...]) -> str:
    return " ".join(f"{byte:02x}" for byte in midi_message_bytes(status, data))


async def send_midi_message_to_port(
    port_address: str,
    status: int,
    data: tuple[int, ...],
) -> None:
    if not port_address.strip():
        raise OSError("no ALSA output port configured")
    if shutil.which("amidi") is None:
        raise OSError("amidi from alsa-utils is required for MIDI output")

    hex_string = format_amidi_hex(status, data)
    process = await asyncio.create_subprocess_exec(
        "amidi",
        "-p",
        port_address,
        "-S",
        hex_string,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    stderr = await process.stderr.read()
    return_code = await process.wait()
    if return_code != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise OSError(detail or f"amidi exited with code {return_code}")

    LOGGER.debug("sent MIDI %s to %s", hex_string, port_address)
