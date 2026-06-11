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


def format_aseqsend_args(port_address: str, status: int, data: tuple[int, ...]) -> list[str]:
    args = ["aseqsend", "-p", port_address, hex(status)]
    args.extend(hex(byte) for byte in data)
    return args


async def _run_sender(command: list[str]) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    stderr = await process.stderr.read()
    return_code = await process.wait()
    if return_code != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise OSError(detail or f"{command[0]} exited with code {return_code}")


async def send_midi_message_to_port(
    port_address: str,
    status: int,
    data: tuple[int, ...],
) -> None:
    if not port_address.strip():
        raise OSError("no ALSA output port configured")

    aseqsend = shutil.which("aseqsend")
    if aseqsend is not None:
        command = format_aseqsend_args(port_address, status, data)
        try:
            await _run_sender(command)
            LOGGER.debug("sent MIDI %s to %s via aseqsend", " ".join(command[3:]), port_address)
            return
        except OSError as exc:
            LOGGER.warning(
                "aseqsend failed for %s (%s); falling back to amidi",
                port_address,
                exc,
            )

    if shutil.which("amidi") is None:
        raise OSError("aseqsend or amidi from alsa-utils is required for MIDI output")

    hex_string = format_amidi_hex(status, data)
    await _run_sender(["amidi", "-p", port_address, "-S", hex_string])
    LOGGER.debug("sent MIDI %s to %s via amidi", hex_string, port_address)
