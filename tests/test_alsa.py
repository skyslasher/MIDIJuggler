from pathlib import Path

from midijuggler.alsa import (
    alsa_config_path_for_config,
    render_master_clock_dmix,
    write_master_clock_dmix_config,
)


def test_alsa_config_path_is_next_to_app_config() -> None:
    assert alsa_config_path_for_config("/etc/midijuggler/config.toml") == Path(
        "/etc/midijuggler/asoundrc"
    )


def test_render_master_clock_dmix_points_to_selected_slave() -> None:
    config = render_master_clock_dmix("plughw:1,0")

    assert "pcm.master_clock" in config
    assert 'pcm "plughw:1,0"' in config
    assert "type dmix" in config


def test_write_master_clock_dmix_config(tmp_path: Path) -> None:
    config_path = tmp_path / "asoundrc"

    write_master_clock_dmix_config(config_path, "default")

    assert 'pcm "default"' in config_path.read_text(encoding="utf-8")
