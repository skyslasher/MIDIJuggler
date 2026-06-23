import struct

import pytest

from midijuggler.osc.protocol import decode_messages, encode_message


def test_encode_decode_float_message_roundtrip() -> None:
    payload = encode_message("/ch/01/mix/01/level", [0.75])
    address, arguments = decode_messages(payload)[0]

    assert address == "/ch/01/mix/01/level"
    assert arguments == (pytest.approx(0.75),)


def test_encode_decode_mixed_arguments_roundtrip() -> None:
    payload = encode_message("/test", [1, 2.5, "hello", True, False])
    address, arguments = decode_messages(payload)[0]

    assert address == "/test"
    assert arguments == (1, pytest.approx(2.5), "hello", True, False)


def test_decode_bundle_extracts_nested_messages() -> None:
    first = encode_message("/one", [1.0])
    second = encode_message("/two", [2.0])
    bundle = b"#bundle\x00" + (b"\x00" * 8)
    bundle += struct.pack(">i", len(first)) + first
    bundle += struct.pack(">i", len(second)) + second

    messages = decode_messages(bundle)

    assert [address for address, _ in messages] == ["/one", "/two"]


def test_decode_rejects_empty_message() -> None:
    with pytest.raises(ValueError, match="empty"):
        decode_messages(b"")


def test_decode_message_without_type_tag() -> None:
    address = b"/ch/1/fdr~~~"
    payload = address + b"\x00" + b"\x00" * 3

    address_text, arguments = decode_messages(payload)[0]

    assert address_text == "/ch/1/fdr~~~"
    assert arguments == ()


def test_wing_control_value_prefers_normalized_float() -> None:
    from midijuggler.osc.protocol import wing_control_value

    assert wing_control_value(("-oo", 0.75, -1.0)) == pytest.approx(0.75)
    assert wing_control_value((-144.0,)) == pytest.approx(-144.0)
