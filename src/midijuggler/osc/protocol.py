"""Minimal OSC 1.0 encode and decode for common mapping types."""

from __future__ import annotations

import struct
from typing import Any


def encode_message(address: str, arguments: list[Any]) -> bytes:
    payload = _pad4(address.encode("utf-8") + b"\x00")
    type_tags = ","
    argument_bytes = b""

    for argument in arguments:
        if isinstance(argument, bool):
            type_tags += "T" if argument else "F"
        elif isinstance(argument, int):
            type_tags += "i"
            argument_bytes += struct.pack(">i", argument)
        elif isinstance(argument, float):
            type_tags += "f"
            argument_bytes += struct.pack(">f", float(argument))
        elif isinstance(argument, str):
            type_tags += "s"
            argument_bytes += _pad4(argument.encode("utf-8") + b"\x00")
        else:
            raise TypeError(f"unsupported OSC argument type: {type(argument)!r}")

    payload += _pad4(type_tags.encode("ascii") + b"\x00")
    payload += argument_bytes
    return payload


def decode_messages(data: bytes) -> list[tuple[str, tuple[Any, ...]]]:
    if data.startswith(b"#bundle"):
        return _decode_bundle(data)
    return [_decode_message(data)]


def _decode_bundle(data: bytes) -> list[tuple[str, tuple[Any, ...]]]:
    if len(data) < 16:
        raise ValueError("OSC bundle is too short")

    messages: list[tuple[str, tuple[Any, ...]]] = []
    offset = 16
    while offset < len(data):
        if offset + 4 > len(data):
            break
        (size,) = struct.unpack(">i", data[offset : offset + 4])
        offset += 4
        if size <= 0 or offset + size > len(data):
            break
        chunk = data[offset : offset + size]
        offset += size
        if chunk:
            messages.append(_decode_message(chunk))
    return messages


def _decode_message(data: bytes) -> tuple[str, tuple[Any, ...]]:
    if not data:
        raise ValueError("empty OSC message")

    address, offset = _read_padded_string(data, 0)
    if offset >= len(data):
        return address, ()

    type_tags, offset = _read_padded_string(data, offset)
    if not type_tags:
        return address, ()
    if not type_tags.startswith(","):
        return address, ()

    arguments: list[Any] = []
    for type_tag in type_tags[1:]:
        if offset + 4 > len(data) and type_tag not in {"T", "F"}:
            break
        if type_tag == "i":
            (value,) = struct.unpack(">i", data[offset : offset + 4])
            arguments.append(value)
            offset += 4
        elif type_tag == "f":
            (value,) = struct.unpack(">f", data[offset : offset + 4])
            arguments.append(value)
            offset += 4
        elif type_tag == "s":
            value, offset = _read_padded_string(data, offset)
            arguments.append(value)
        elif type_tag == "b":
            (size,) = struct.unpack(">i", data[offset : offset + 4])
            offset += 4
            blob_end = offset + size
            offset = ((blob_end + 3) // 4) * 4
        elif type_tag == "T":
            arguments.append(True)
        elif type_tag == "F":
            arguments.append(False)
        else:
            raise ValueError(f"unsupported OSC type tag: {type_tag!r}")

    return address, tuple(arguments)


def _read_padded_string(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        raise ValueError("OSC string is not null-terminated")
    value = data[offset:end].decode("utf-8")
    next_offset = ((end + 1 + 3) // 4) * 4
    return value, next_offset


def _pad4(data: bytes) -> bytes:
    padding = (4 - (len(data) % 4)) % 4
    return data + (b"\x00" * padding)


def first_numeric_osc_argument(arguments: tuple[Any, ...] | list[Any]) -> float | None:
    for argument in arguments:
        if isinstance(argument, bool):
            return 1.0 if argument else 0.0
        if isinstance(argument, (int, float)):
            return float(argument)
    return None


def wing_control_value(arguments: tuple[Any, ...] | list[Any]) -> float | None:
    """Return the normalized Wing control value from sff-style feedback."""

    floats = [
        float(argument)
        for argument in arguments
        if isinstance(argument, (int, float)) and not isinstance(argument, bool)
    ]
    if len(floats) >= 2:
        return floats[0]
    if floats:
        return floats[-1]
    return first_numeric_osc_argument(arguments)
