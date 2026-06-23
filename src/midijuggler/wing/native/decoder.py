"""Decode Wing native/binary protocol streams."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum, auto

from midijuggler.wing.native.protocol import CHANNEL_ID_BASE, ESCAPE_CODE, NUM_CHANNELS


class WingDecodeKind(Enum):
    NODE_ID = auto()
    NODE_DATA = auto()
    NODE_DEF = auto()
    REQUEST_END = auto()


@dataclass(frozen=True)
class WingNodeData:
    node_id: int
    float_value: float | None = None
    int_value: int | None = None
    string_value: str | None = None


@dataclass(frozen=True)
class WingNodeDef:
    node_id: int
    parent_id: int
    index: int
    name: str
    long_name: str
    flags: int

    @property
    def is_node(self) -> bool:
        return ((self.flags >> 4) & 0x0F) == 0


class WingStreamDecoder:
    """Incremental decoder for one Wing native TCP stream."""

    def __init__(self) -> None:
        self._escape = False
        self._channel = -1
        self._pending_escape: int | None = None
        self._current_node_id = 0
        self._pending: list[int] = []

    @property
    def current_node_id(self) -> int:
        return self._current_node_id

    def feed(self, data: bytes) -> list[tuple[WingDecodeKind, object]]:
        events: list[tuple[WingDecodeKind, object]] = []
        for byte in data:
            events.extend(self._feed_byte(byte))
        return events

    def _feed_byte(self, byte: int) -> list[tuple[WingDecodeKind, object]]:
        if self._pending_escape is not None:
            value = self._pending_escape
            self._pending_escape = None
            return self._consume_data_byte(value)

        if not self._escape:
            if byte == ESCAPE_CODE:
                self._escape = True
                return []
            if self._channel >= 0:
                return self._consume_data_byte(byte)
            return []

        self._escape = False
        if byte == ESCAPE_CODE:
            if self._channel >= 0:
                return self._consume_data_byte(ESCAPE_CODE)
            return []
        if byte == ESCAPE_CODE - 1:
            self._pending_escape = ESCAPE_CODE
            return []
        if CHANNEL_ID_BASE <= byte < CHANNEL_ID_BASE + NUM_CHANNELS:
            self._channel = byte - CHANNEL_ID_BASE
            self._pending.clear()
            return []
        if self._channel >= 0:
            self._pending_escape = byte
            return []
        return []

    def _consume_data_byte(self, byte: int) -> list[tuple[WingDecodeKind, object]]:
        self._pending.append(byte)
        if not self._pending:
            return []

        command = self._pending[0]
        if command == 0xDE:
            self._pending.clear()
            return [(WingDecodeKind.REQUEST_END, None)]
        if command == 0xD7 and len(self._pending) >= 5:
            node_id = struct.unpack(">i", bytes(self._pending[1:5]))[0]
            self._current_node_id = node_id
            self._pending.clear()
            return [(WingDecodeKind.NODE_ID, node_id)]
        if command in {0xD5, 0xD6} and len(self._pending) >= 5:
            value = struct.unpack(">f", bytes(self._pending[1:5]))[0]
            self._pending.clear()
            return [
                (
                    WingDecodeKind.NODE_DATA,
                    WingNodeData(self._current_node_id, float_value=value),
                )
            ]
        if command == 0xD3 and len(self._pending) >= 3:
            value = struct.unpack(">h", bytes(self._pending[1:3]))[0]
            self._pending.clear()
            return [
                (
                    WingDecodeKind.NODE_DATA,
                    WingNodeData(self._current_node_id, int_value=value),
                )
            ]
        if command == 0xD4 and len(self._pending) >= 5:
            value = struct.unpack(">i", bytes(self._pending[1:5]))[0]
            self._pending.clear()
            return [
                (
                    WingDecodeKind.NODE_DATA,
                    WingNodeData(self._current_node_id, int_value=value),
                )
            ]
        if command <= 0x3F and len(self._pending) >= 1:
            value = command
            self._pending.clear()
            return [
                (
                    WingDecodeKind.NODE_DATA,
                    WingNodeData(self._current_node_id, int_value=value),
                )
            ]
        if command == 0xDF:
            if len(self._pending) < 3:
                return []
            length = struct.unpack(">H", bytes(self._pending[1:3]))[0]
            total = 3 + length
            if length == 0 and len(self._pending) >= 7:
                length = struct.unpack(">I", bytes(self._pending[3:7]))[0]
                total = 7 + length
            if len(self._pending) < total:
                return []
            raw = bytes(self._pending[3:total])
            self._pending.clear()
            return [(WingDecodeKind.NODE_DEF, parse_node_definition(raw))]
        return []


def parse_node_definition(raw: bytes) -> WingNodeDef:
    offset = 0
    parent_id = struct.unpack(">i", raw[offset : offset + 4])[0]
    offset += 4
    node_id = struct.unpack(">i", raw[offset : offset + 4])[0]
    offset += 4
    index = struct.unpack(">H", raw[offset : offset + 2])[0]
    offset += 2
    name_len = raw[offset]
    offset += 1
    name = raw[offset : offset + name_len].decode("ascii", errors="replace")
    offset += name_len
    long_name_len = raw[offset]
    offset += 1
    long_name = raw[offset : offset + long_name_len].decode("ascii", errors="replace")
    offset += long_name_len
    flags = struct.unpack(">H", raw[offset : offset + 2])[0]
    return WingNodeDef(
        node_id=node_id,
        parent_id=parent_id,
        index=index,
        name=name,
        long_name=long_name,
        flags=flags,
    )
