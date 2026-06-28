from pathlib import Path

import pytest

from midijuggler.system_info import (
    is_dmix_pcm_name,
    list_click_wavs,
    normalize_midi_port_id,
    parse_aconnect_ports,
    parse_aplay_devices,
    parse_dmix_pcm_devices,
)


def test_parse_aplay_devices_returns_stable_card_ids() -> None:
    devices = parse_aplay_devices(
        """
        **** List of PLAYBACK Hardware Devices ****
        card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
        card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
        """
    )

    assert devices[0] == {
        "id": "",
        "label": "default (software/mixed)",
        "mode": "alias",
    }
    assert devices[1]["id"] == "plughw:CARD=Headphones,DEV=0"
    assert devices[1]["resolved_device"] == "plughw:0,0"
    assert devices[1]["card_name"] == "Headphones"
    assert devices[2]["id"] == "plughw:CARD=Device,DEV=0"
    assert devices[2]["resolved_device"] == "plughw:1,0"
    assert devices[2]["card_name"] == "Device"


def test_is_dmix_pcm_name_detects_common_dmix_devices() -> None:
    assert is_dmix_pcm_name("dmix")
    assert is_dmix_pcm_name("dmix:CARD=Device,DEV=0")
    assert is_dmix_pcm_name("master_clock_dmix")
    assert not is_dmix_pcm_name("default")
    assert not is_dmix_pcm_name("plughw:CARD=Device,DEV=0")


def test_parse_dmix_pcm_devices_returns_software_dmix_pcms() -> None:
    devices = parse_dmix_pcm_devices(
        """default
    Default Audio Device
dmix:CARD=Device,DEV=0
    Direct mix multichannel
plughw:CARD=Device,DEV=0
    Hardware device with all software conversions
master_clock_dmix
    MIDIJuggler click mix
"""
    )

    assert [device["id"] for device in devices] == [
        "dmix:CARD=Device,DEV=0",
        "master_clock_dmix",
    ]
    assert devices[0]["mode"] == "alias"
    assert devices[0]["label"] == "Direct mix multichannel (dmix:CARD=Device,DEV=0)"


def test_parse_aconnect_ports_returns_all_client_addresses() -> None:
    ports = parse_aconnect_ports(
        """
        client 0: 'System' [type=kernel]
            0 'Timer'
        client 20: 'MIDIJuggler' [type=user]
            0 'MIDIJuggler In'
            1 'MIDIJuggler Out'
        client 21: 'MIDIJuggler' [type=user]
            0 'MIDIJuggler In'
        """
    )

    assert ports == [
        {
            "id": "MIDIJuggler In",
            "address": "20:0",
            "label": "MIDIJuggler / MIDIJuggler In (20:0)",
            "client": "MIDIJuggler",
        },
        {
            "id": "MIDIJuggler Out",
            "address": "20:1",
            "label": "MIDIJuggler / MIDIJuggler Out (20:1)",
            "client": "MIDIJuggler",
        },
        {
            "id": "MIDIJuggler In",
            "address": "21:0",
            "label": "MIDIJuggler / MIDIJuggler In (21:0)",
            "client": "MIDIJuggler",
        },
    ]


def test_parse_aconnect_ports_keeps_same_name_on_different_addresses() -> None:
    ports = parse_aconnect_ports(
        """
        client 24: 'X-TOUCHMINI' [type=kernel]
            0 'X-TOUCH MINI'
            1 'X-TOUCH MINI'
        """
    )

    assert [port["address"] for port in ports] == ["24:0", "24:1"]


def test_normalize_midi_port_id_migrates_legacy_address(monkeypatch) -> None:
    ports = parse_aconnect_ports(
        """
        client 24: 'X-TOUCHMINI' [type=kernel]
            0 'X-TOUCH MINI'
        """
    )
    monkeypatch.setattr(
        "midijuggler.system_info.list_midi_input_ports",
        lambda: ports,
    )

    assert normalize_midi_port_id("24:0", inputs=True) == "X-TOUCH MINI"


def test_list_midi_input_ports_falls_back_to_aconnect_when_mido_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from midijuggler.system_info import list_midi_input_ports

    monkeypatch.setattr(
        "midijuggler.system_info._list_mido_ports",
        lambda *, inputs: [] if inputs else [],
    )
    monkeypatch.setattr(
        "midijuggler.system_info._aconnect_list",
        lambda *args: """
        client 24: 'X-TOUCHMINI' [type=kernel]
            0 'X-TOUCH MINI'
        """,
    )

    ports = list_midi_input_ports()

    assert ports == [
        {
            "id": "X-TOUCH MINI",
            "address": "24:0",
            "label": "X-TOUCHMINI / X-TOUCH MINI (24:0)",
            "client": "X-TOUCHMINI",
        }
    ]


def test_list_click_wavs_finds_wav_files(tmp_path: Path) -> None:
    (tmp_path / "click.wav").write_text("not really wav", encoding="utf-8")
    (tmp_path / "accent.WAV").write_text("not really wav", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("ignore", encoding="utf-8")

    wavs = list_click_wavs(tmp_path)

    assert wavs == [
        {"path": str(tmp_path / "accent.WAV"), "label": "accent.WAV"},
        {"path": str(tmp_path / "click.wav"), "label": "click.wav"},
    ]
