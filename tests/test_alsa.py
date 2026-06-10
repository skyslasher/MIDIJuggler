from pathlib import Path

from midijuggler.alsa import (
    alsa_mode_for_device,
    alsa_config_path_for_config,
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
    assert 'pcm "hw:1,0"' in config
    assert "type dmix" in config


def test_render_master_clock_pcm_uses_alias_for_soft_device() -> None:
    config = render_master_clock_pcm("default")

    assert "pcm.master_clock" in config
    assert "type plug" in config
    assert 'slave.pcm "default"' in config
    assert "type dmix" not in config


def test_alsa_mode_for_device_detects_hardware() -> None:
    assert alsa_mode_for_device("plughw:1,0") == "dmix"
    assert alsa_mode_for_device("hw:1,0") == "dmix"
    assert alsa_mode_for_device("default") == "alias"
    assert alsa_mode_for_device("dmix") == "alias"


def test_write_master_clock_dmix_config(tmp_path: Path) -> None:
    config_path = tmp_path / "asoundrc"

    write_master_clock_pcm_config(config_path, "default")

    assert 'slave.pcm "default"' in config_path.read_text(encoding="utf-8")
