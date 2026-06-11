import asyncio

import pytest

from midijuggler.midi.output import (
    format_amidi_hex,
    format_aseqsend_args,
    is_sequencer_port_address,
    send_midi_message_to_port,
)


def test_format_amidi_hex_encodes_status_and_data() -> None:
    assert format_amidi_hex(0xB0, (1, 64)) == "b0 01 40"


def test_is_sequencer_port_address() -> None:
    assert is_sequencer_port_address("20:0")
    assert not is_sequencer_port_address("hw:1,0,0")


def test_format_aseqsend_args_encodes_status_and_data() -> None:
    assert format_aseqsend_args("24:1", 0x90, (60, 100)) == [
        "aseqsend",
        "-p",
        "24:1",
        "90 3C 64",
    ]


def test_send_midi_message_to_port_uses_mido(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, int, tuple[int, ...]]] = []

    def fake_send(port_name: str, status: int, data: tuple[int, ...]) -> None:
        sent.append((port_name, status, data))

    monkeypatch.setattr("midijuggler.midi.mido_io.send_mido_message", fake_send)

    asyncio.run(send_midi_message_to_port("X-TOUCH MINI MIDI 1", 0x90, (60, 100)))

    assert sent == [("X-TOUCH MINI MIDI 1", 0x90, (60, 100))]
