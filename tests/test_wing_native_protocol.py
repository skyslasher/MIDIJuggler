import asyncio
import struct

import pytest

from midijuggler.wing.native.decoder import WingDecodeKind, WingStreamDecoder, parse_node_definition
from midijuggler.wing.native.protocol import (
    encode_keepalive,
    encode_request_node_definition,
    encode_set_float,
)


def test_encode_keepalive_selects_audio_engine_channel() -> None:
    assert encode_keepalive() == bytes([0xDF, 0xD1])


def test_encode_set_float_prefixes_channel_and_node_hash() -> None:
    payload = encode_set_float(0x12345678, 0.5)

    assert payload.startswith(bytes([0xDF, 0xD1, 0xD7]))
    assert payload.endswith(struct.pack(">f", 0.5))


def test_encode_request_root_node_definition() -> None:
    payload = encode_request_node_definition(0)

    assert payload == bytes([0xDF, 0xD1, 0xDA, 0xDD])


def test_decoder_parses_spontaneous_float_update() -> None:
    decoder = WingStreamDecoder()
    events = decoder.feed(encode_set_float(0x01020304, 0.75))

    kinds = [kind for kind, _payload in events]
    assert WingDecodeKind.NODE_ID in kinds
    data_events = [payload for kind, payload in events if kind == WingDecodeKind.NODE_DATA]
    assert len(data_events) == 1
    assert data_events[0].node_id == 0x01020304
    assert data_events[0].float_value == pytest.approx(0.75)


def test_parse_node_definition_reads_name_and_id() -> None:
    raw = struct.pack(">i", 0) + struct.pack(">i", 42) + struct.pack(">H", 1)
    raw += bytes([3]) + b"fdr" + bytes([0]) + struct.pack(">H", 0x0030)

    node = parse_node_definition(raw)

    assert node.node_id == 42
    assert node.name == "fdr"
    assert node.is_node is False
