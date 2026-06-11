"""MIDI port I/O via mido and python-rtmidi."""

from __future__ import annotations

import logging
import time
from typing import Any

from midijuggler.midi.output import midi_message_bytes

LOGGER = logging.getLogger(__name__)


class MidoUnavailableError(OSError):
    """Raised when mido/python-rtmidi are not installed."""


def mido_available() -> bool:
    try:
        import mido  # noqa: F401
        import rtmidi  # noqa: F401
    except ImportError:
        return False
    return True


def _require_mido() -> Any:
    if not mido_available():
        raise MidoUnavailableError(
            "mido and python-rtmidi are required; install with pip install 'midijuggler[midi]'"
        )
    import mido

    return mido


def mido_message_to_status_data(message: Any) -> tuple[int, tuple[int, ...]] | None:
    if message.type == "clock":
        return 0xF8, ()

    raw = tuple(message.bytes())
    if not raw:
        return None
    return raw[0], raw[1:]


def list_mido_port_entries(*, inputs: bool) -> list[dict[str, str]]:
    mido = _require_mido()
    names = mido.get_input_names() if inputs else mido.get_output_names()
    entries: list[dict[str, str]] = []
    for name in names:
        port_id = _infer_config_port_id(name)
        entries.append(
            {
                "id": port_id,
                "mido_name": name,
                "address": name,
                "label": name,
                "client": _infer_client_name(name),
            }
        )
    return entries


def _infer_client_name(mido_name: str) -> str:
    if " " not in mido_name:
        return mido_name
    return mido_name.split()[0]


def _infer_config_port_id(mido_name: str) -> str:
    parts = mido_name.split()
    if len(parts) >= 4 and len(parts) % 2 == 0:
        midpoint = len(parts) // 2
        first_half = " ".join(parts[:midpoint])
        second_half = " ".join(parts[midpoint:])
        if first_half == second_half:
            return second_half
    return mido_name


def is_mido_port_listed(port_name: str, *, inputs: bool) -> bool:
    mido = _require_mido()
    names = mido.get_input_names() if inputs else mido.get_output_names()
    return port_name in names


def open_mido_input(port_name: str) -> Any:
    mido = _require_mido()
    try:
        return mido.open_input(port_name)
    except OSError as exc:
        raise OSError(f"cannot open MIDI input port {port_name!r}") from exc


def open_mido_output(port_name: str) -> Any:
    mido = _require_mido()
    try:
        return mido.open_output(port_name)
    except OSError as exc:
        raise OSError(f"cannot open MIDI output port {port_name!r}") from exc


def poll_mido_input(port: Any, timeout: float = 0.05) -> Any | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = port.poll()
        if message is not None:
            return message
        time.sleep(0.001)
    return None


def close_mido_port(port: Any) -> None:
    if port is None:
        return
    port.close()


def send_mido_message(port_name: str, status: int, data: tuple[int, ...]) -> None:
    mido = _require_mido()
    message = mido.Message.from_bytes(midi_message_bytes(status, data))
    with mido.open_output(port_name) as port:
        port.send(message)
    LOGGER.debug("sent MIDI %s to %s via mido", message.hex(), port_name)
