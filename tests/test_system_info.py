from pathlib import Path

from midijuggler.system_info import list_click_wavs, parse_aconnect_ports, parse_aplay_devices


def test_parse_aplay_devices_returns_plughw_ids() -> None:
    devices = parse_aplay_devices(
        """
        **** List of PLAYBACK Hardware Devices ****
        card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
        card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
        """
    )

    assert devices == [
        {"id": "", "label": "default (software/mixed)", "mode": "alias"},
        {
            "id": "plughw:0,0",
            "label": "Headphones / bcm2835 Headphones (plughw:0,0)",
            "mode": "dmix",
        },
        {
            "id": "plughw:1,0",
            "label": "Device / USB Audio (plughw:1,0)",
            "mode": "dmix",
        },
    ]


def test_parse_aconnect_ports_returns_unique_port_names() -> None:
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
            "label": "MIDIJuggler / MIDIJuggler In",
            "client": "MIDIJuggler",
        },
        {
            "id": "MIDIJuggler Out",
            "label": "MIDIJuggler / MIDIJuggler Out",
            "client": "MIDIJuggler",
        },
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
