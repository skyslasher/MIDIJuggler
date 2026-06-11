import asyncio
from unittest.mock import AsyncMock

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


def test_send_midi_message_to_port_requires_aseqsend_for_sequencer_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("midijuggler.midi.output.shutil.which", lambda _: None)

    with pytest.raises(OSError, match="aseqsend is required"):
        asyncio.run(send_midi_message_to_port("20:0", 0x90, (60, 100)))


def test_format_aseqsend_args_encodes_status_and_data() -> None:
    assert format_aseqsend_args("24:1", 0x90, (60, 100)) == [
        "aseqsend",
        "-p",
        "24:1",
        "90 3C 64",
    ]


def test_send_midi_message_to_port_prefers_aseqsend(monkeypatch: pytest.MonkeyPatch) -> None:
    def which(command: str) -> str | None:
        if command == "aseqsend":
            return "/usr/bin/aseqsend"
        if command == "amidi":
            return "/usr/bin/amidi"
        return None

    monkeypatch.setattr("midijuggler.midi.output.shutil.which", which)

    process = AsyncMock()
    process.stderr.read = AsyncMock(return_value=b"")
    process.wait = AsyncMock(return_value=0)
    captured: list[list[str]] = []

    async def fake_exec(*args, **_kwargs):
        captured.append(list(args))
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    asyncio.run(send_midi_message_to_port("24:1", 0x90, (60, 100)))

    assert captured == [["aseqsend", "-p", "24:1", "90 3C 64"]]


def test_send_midi_message_to_port_invokes_amidi(monkeypatch: pytest.MonkeyPatch) -> None:
    def which(command: str) -> str | None:
        if command == "aseqsend":
            return None
        if command == "amidi":
            return "/usr/bin/amidi"
        return None

    monkeypatch.setattr("midijuggler.midi.output.shutil.which", which)

    process = AsyncMock()
    process.stderr.read = AsyncMock(return_value=b"")
    process.wait = AsyncMock(return_value=0)

    async def fake_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    asyncio.run(send_midi_message_to_port("hw:1,0,0", 0x90, (60, 100)))

    assert process.wait.await_count == 1
