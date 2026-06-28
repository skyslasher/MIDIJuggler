from pathlib import Path

from midijuggler.alsa import (
    alsa_mode_for_device,
    alsa_config_path_for_config,
    normalize_alsa_output_device,
    render_master_clock_pcm,
    render_master_clock_dmix,
    write_master_clock_pcm_config,
)


def test_alsa_config_path_is_next_to_app_config() -> None:
    assert alsa_config_path_for_config("/etc/midijuggler/config.toml") == Path(
        "/etc/midijuggler/asoundrc"
    )


def test_render_master_clock_dmix_points_to_selected_slave() -> None:
    config = render_master_clock_dmix("plughw:1,0")

    assert "pcm.master_clock" in config
    assert "pcm.master_clock_dmix" in config
    assert 'slave.pcm "master_clock_dmix"' in config
    assert 'pcm "hw:1,0"' in config
    assert "type plug" in config
    assert "type dmix" in config


def test_render_master_clock_pcm_uses_alias_for_soft_device() -> None:
    config = render_master_clock_pcm("default")

    assert "pcm.master_clock" in config
    assert "type plug" in config
    assert 'slave.pcm "default"' in config
    assert "type dmix" not in config


def test_render_master_clock_dmix_supports_stable_card_device_id() -> None:
    config = render_master_clock_dmix("plughw:CARD=Device,DEV=0")

    assert 'pcm "hw:CARD=Device,DEV=0"' in config


def test_normalize_alsa_output_device_migrates_legacy_plughw_id() -> None:
    devices = [
        {"id": "", "label": "default", "mode": "alias"},
        {
            "id": "plughw:CARD=Device,DEV=0",
            "resolved_device": "plughw:1,0",
            "card_number": "1",
            "device_index": "0",
            "card_name": "Device",
            "device_name": "USB Audio",
            "mode": "dmix",
        },
    ]

    assert (
        normalize_alsa_output_device("plughw:1,0", devices=devices)
        == "plughw:CARD=Device,DEV=0"
    )


def test_alsa_mode_for_device_detects_hardware() -> None:
    assert alsa_mode_for_device("plughw:1,0") == "dmix"
    assert alsa_mode_for_device("plughw:CARD=Device,DEV=0") == "dmix"
    assert alsa_mode_for_device("hw:1,0") == "dmix"
    assert alsa_mode_for_device("default") == "alias"
    assert alsa_mode_for_device("dmix") == "alias"


def test_normalize_alsa_output_device_keeps_dmix_pcm_id() -> None:
    devices = [
        {"id": "", "label": "default", "mode": "alias"},
        {
            "id": "dmix:CARD=Device,DEV=0",
            "resolved_device": "dmix:CARD=Device,DEV=0",
            "label": "Direct mix (dmix:CARD=Device,DEV=0)",
            "mode": "alias",
        },
    ]

    assert (
        normalize_alsa_output_device("dmix:CARD=Device,DEV=0", devices=devices)
        == "dmix:CARD=Device,DEV=0"
    )
    assert alsa_mode_for_device("dmix:CARD=Device,DEV=0") == "alias"


def test_lookup_alsa_output_device_matches_case_insensitive_pcm_id() -> None:
    from midijuggler.alsa import lookup_alsa_output_device

    devices = [
        {
            "id": "dmix:CARD=WING,DEV=0",
            "resolved_device": "dmix:CARD=WING,DEV=0",
            "label": "dmix",
            "mode": "alias",
        }
    ]

    matched = lookup_alsa_output_device("dmix:CARD=WING,dev=0", devices=devices)
    assert matched is not None
    assert matched["id"] == "dmix:CARD=WING,DEV=0"


def test_write_master_clock_dmix_config(tmp_path: Path) -> None:
    config_path = tmp_path / "asoundrc"

    write_master_clock_pcm_config(config_path, "default")

    assert 'slave.pcm "default"' in config_path.read_text(encoding="utf-8")
