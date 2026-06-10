from pathlib import Path

from midijuggler.system_info import list_click_wavs, parse_aplay_devices


def test_parse_aplay_devices_returns_plughw_ids() -> None:
    devices = parse_aplay_devices(
        """
        **** List of PLAYBACK Hardware Devices ****
        card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
        card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
        """
    )

    assert devices == [
        {"id": "", "label": "default"},
        {
            "id": "plughw:0,0",
            "label": "Headphones / bcm2835 Headphones (plughw:0,0)",
        },
        {
            "id": "plughw:1,0",
            "label": "Device / USB Audio (plughw:1,0)",
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
