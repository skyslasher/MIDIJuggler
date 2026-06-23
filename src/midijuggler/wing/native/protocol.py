"""Low-level Wing native/binary protocol encoding."""

from __future__ import annotations

import struct
from typing import Iterable

ESCAPE_CODE = 0xDF
CHANNEL_ID_BASE = 0xD0
NUM_CHANNELS = 14
# Wing remote protocol: audio-engine parameters (faders, etc.) use comm channel 2.
AUDIO_ENGINE_CHANNEL = 2
WING_NATIVE_PORT = 2222


def _escape_payload(data: Iterable[int]) -> bytes:
    escaped = bytearray()
    pending_escape = False
    data_bytes = [value & 0xFF for value in data]
    index = 0
    while index < len(data_bytes):
        byte = data_bytes[index]
        if byte == ESCAPE_CODE:
            escaped.append(ESCAPE_CODE)
            pending_escape = True
            index += 1
            continue
        if pending_escape and CHANNEL_ID_BASE <= byte < CHANNEL_ID_BASE + NUM_CHANNELS:
            escaped.append(ESCAPE_CODE - 1)
            pending_escape = False
            continue
        pending_escape = False
        escaped.append(byte)
        index += 1
    if pending_escape:
        escaped.append(ESCAPE_CODE - 1)
    return bytes(escaped)


def encode_node_id(node_id: int, suffix: int | None = None) -> bytes:
    payload = bytearray([0xD7])
    payload.extend(_escape_payload(struct.pack(">i", node_id)))
    if suffix is not None:
        payload.append(suffix)
    return bytes(payload)


def encode_channel_select(channel: int = AUDIO_ENGINE_CHANNEL) -> bytes:
    if channel < 1 or channel > NUM_CHANNELS:
        raise ValueError(f"invalid Wing native channel: {channel}")
    return bytes([ESCAPE_CODE, CHANNEL_ID_BASE + channel])


def encode_channel_payload(channel: int, payload: bytes) -> bytes:
    return encode_channel_select(channel) + _escape_payload(payload)


def encode_keepalive(channel: int = AUDIO_ENGINE_CHANNEL) -> bytes:
    return encode_channel_select(channel)


def encode_request_node_definition(node_id: int = 0) -> bytes:
    if node_id == 0:
        return bytes([0xDA, 0xDD])
    return encode_node_id(node_id, 0xDD)


def encode_request_node_data(node_id: int) -> bytes:
    return encode_node_id(node_id, 0xDC)


def encode_set_float(node_id: int, value: float, *, raw: bool = False) -> bytes:
    """Encode a float write. Use raw=True (0xD6) for normalized 0..1 fader positions."""

    suffix = 0xD6 if raw else 0xD5
    return encode_node_id(node_id, suffix) + struct.pack(">f", value)


def encode_set_int(node_id: int, value: int) -> bytes:
    payload = bytearray(encode_node_id(node_id))
    if 0 <= value <= 0x3F:
        payload.append(value)
    elif -32768 <= value <= 32767:
        payload.extend([0xD3, *struct.pack(">h", value)])
    else:
        payload.extend([0xD4, *struct.pack(">i", value)])
    return bytes(payload)
