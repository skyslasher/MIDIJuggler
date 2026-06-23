import asyncio
import struct

import pytest

from midijuggler.wing.native.client import WingNativeClient
from midijuggler.wing.native.decoder import WingDecodeKind, WingStreamDecoder, parse_node_definition
from midijuggler.wing.native.protocol import (
    encode_keepalive,
    encode_request_node_definition,
    encode_set_float,
)


def _node_def_raw(*, node_id: int, name: str, parent_id: int = 0) -> bytes:
    raw = struct.pack(">i", parent_id) + struct.pack(">i", node_id) + struct.pack(">H", 0)
    raw += bytes([len(name)]) + name.encode("ascii") + bytes([0]) + struct.pack(">H", 0x0030)
    return raw


def _wire_node_def_response(raw: bytes) -> bytes:
    return bytes([0xDF, 0xDE]) + struct.pack(">H", len(raw)) + raw


def test_encode_keepalive_selects_audio_engine_channel() -> None:
    assert encode_keepalive() == bytes([0xDF, 0xD1])


def test_encode_set_float_uses_node_hash_prefix() -> None:
    payload = encode_set_float(0x12345678, 0.5)

    assert payload.startswith(bytes([0xD7]))
    assert payload.endswith(struct.pack(">f", 0.5))


def test_encode_request_root_node_definition() -> None:
    payload = encode_request_node_definition(0)

    assert payload == bytes([0xDA, 0xDD])


def test_encode_request_child_node_definition() -> None:
    payload = encode_request_node_definition(0x12345678)

    assert payload.startswith(bytes([0xD7, 0x12, 0x34, 0x56, 0x78, 0xDD]))


def test_decoder_parses_spontaneous_float_update() -> None:
    decoder = WingStreamDecoder()
    events = decoder.feed(bytes([0xDF, 0xD1]) + encode_set_float(0x01020304, 0.75))

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


def test_decoder_parses_node_definition_stream_with_request_end() -> None:
    ch = _wire_node_def_response(_node_def_raw(node_id=10, name="ch"))
    stream = bytes([0xDF, 0xD1]) + ch + bytes([0xDE])

    decoder = WingStreamDecoder()
    events = decoder.feed(stream)

    kinds = [kind for kind, _payload in events]
    assert kinds.count(WingDecodeKind.NODE_DEF) == 1
    assert kinds[-1] == WingDecodeKind.REQUEST_END
    node = next(payload for kind, payload in events if kind == WingDecodeKind.NODE_DEF)
    assert node.node_id == 10
    assert node.name == "ch"


def test_client_handle_events_completes_list_children_from_wire_stream() -> None:
    async def scenario() -> list[object]:
        client = WingNativeClient("127.0.0.1")

        async def noop_write(_payload: bytes) -> None:
            return

        client._write = noop_write  # type: ignore[method-assign]  # noqa: SLF001

        ch = _wire_node_def_response(_node_def_raw(node_id=42, name="ch"))
        stream = bytes([0xDF, 0xD1]) + ch + bytes([0xDE])

        pending = asyncio.create_task(client.list_children(0))
        await asyncio.sleep(0)
        events = client._decoder.feed(stream)  # noqa: SLF001
        client.handle_events(events)
        return await pending

    children = asyncio.run(scenario())

    assert len(children) == 1
    assert children[0].node_id == 42
    assert children[0].name == "ch"
