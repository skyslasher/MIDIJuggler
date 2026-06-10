from pathlib import Path

import pytest

from midijuggler.config import (
    MasterClockConfig,
    load_config,
    parse_config,
    save_gpio_adapter_options,
    save_master_clock_config,
)


def test_parse_config_reads_web_adapters_and_mappings() -> None:
    config = parse_config(
        {
            "web": {"host": "127.0.0.1", "port": 9090},
            "master_clock": {
                "enabled": True,
                "bpm": 118.5,
                "output_targets": ["usb_midi", "rtp_midi"],
                "click_interval": "eighth",
            },
            "adapters": {"gpio": {"enabled": True, "pins": [17]}},
            "mappings": [
                {
                    "id": "switch",
                    "source": "gpio:pin17",
                    "target": "usb_midi:cc:1:64",
                    "invert": True,
                }
            ],
        }
    )

    assert config.web.host == "127.0.0.1"
    assert config.web.port == 9090
    assert config.master_clock.enabled is True
    assert config.master_clock.bpm == 118.5
    assert config.master_clock.output_targets == ["usb_midi", "rtp_midi"]
    assert config.master_clock.click_interval == "eighth"
    assert config.adapters["gpio"].enabled is True
    assert config.adapters["gpio"].kind == "gpio"
    assert config.adapters["gpio"].options["pins"] == [17]
    assert config.adapters["osc"].enabled is False
    assert config.mappings[0].id == "switch"
    assert config.mappings[0].invert is True


def test_parse_config_supports_named_adapter_instances() -> None:
    config = parse_config(
        {
            "adapters": {
                "osc": {"enabled": True, "listen_port": 9000},
                "osc_pedalboard": {
                    "type": "osc",
                    "enabled": True,
                    "listen_port": 9001,
                },
                "usb_stage": {
                    "type": "usb_midi",
                    "enabled": True,
                    "output_port": "Stage MIDI",
                },
                "rtp_remote": {
                    "type": "rtp_midi",
                    "enabled": False,
                    "session_name": "Remote",
                },
            }
        }
    )

    assert config.adapters["osc"].kind == "osc"
    assert config.adapters["osc"].options["listen_port"] == 9000
    assert config.adapters["osc_pedalboard"].kind == "osc"
    assert config.adapters["osc_pedalboard"].options["listen_port"] == 9001
    assert config.adapters["usb_stage"].kind == "usb_midi"
    assert config.adapters["usb_stage"].options["output_port"] == "Stage MIDI"
    assert config.adapters["rtp_remote"].kind == "rtp_midi"
    assert config.adapters["rtp_remote"].enabled is False


def test_load_config_reads_toml_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [web]
        host = "0.0.0.0"
        port = 8081

        [[mappings]]
        id = "pedal"
        source = "osc:/pedal"
        target = "usb_midi:cc:1:11"
        input_min = 0.0
        input_max = 1.0
        output_min = 0.0
        output_max = 127.0
        """,
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.web.port == 8081
    assert config.mappings[0].target == "usb_midi:cc:1:11"


def test_save_gpio_adapter_options_replaces_gpio_section(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [web]
        port = 8080

        [adapters.gpio]
        enabled = true
        pins = [17]
        active_low = true
        bounce_ms = 25
        poll_interval_ms = 5

        [adapters.osc]
        enabled = false
        """,
        encoding="utf-8",
    )

    save_gpio_adapter_options(
        config_file,
        {
            "pins": [22, 27],
            "active_low": False,
            "bounce_ms": 10,
            "poll_interval_ms": 2,
        },
    )

    config = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert config.adapters["gpio"].options == {
        "pins": [22, 27],
        "active_low": False,
        "bounce_ms": 10,
        "poll_interval_ms": 2,
    }
    assert config.adapters["osc"].enabled is False
    saved_lines = saved_text.splitlines()
    poll_line_index = saved_lines.index("poll_interval_ms = 2")
    assert saved_lines[poll_line_index + 1] == ""
    assert saved_lines[poll_line_index + 2].strip() == "[adapters.osc]"


def test_save_master_clock_config_replaces_master_clock_section(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [web]
        port = 8080

        [master_clock]
        enabled = false
        bpm = 120.0

        [adapters.gpio]
        enabled = true
        pins = [17]
        """,
        encoding="utf-8",
    )

    save_master_clock_config(
        config_file,
        MasterClockConfig(
            enabled=True,
            bpm=128.5,
            bpm_min=40.0,
            bpm_max=240.0,
            output_targets=["usb_midi", "rtp_midi"],
            click_enabled=True,
            click_interval="half",
            click_wav="/etc/midijuggler/click.wav",
        ),
    )

    config = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert config.master_clock.enabled is True
    assert config.master_clock.bpm == pytest.approx(128.5)
    assert config.master_clock.output_targets == ["usb_midi", "rtp_midi"]
    assert config.master_clock.click_interval == "half"
    assert 'output_targets = ["usb_midi", "rtp_midi"]' in saved_text
    saved_lines = saved_text.splitlines()
    click_device_index = saved_lines.index('click_audio_device = ""')
    assert saved_lines[click_device_index + 1] == ""
    assert saved_lines[click_device_index + 2].strip() == "[adapters.gpio]"


def test_parse_config_rejects_incomplete_mapping() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        parse_config({"mappings": [{"id": "broken", "source": "gpio:pin17"}]})


def test_parse_config_rejects_invalid_master_clock_interval() -> None:
    with pytest.raises(ValueError, match="click_interval"):
        parse_config({"master_clock": {"click_interval": "triplet"}})


def test_parse_config_rejects_unknown_adapter_instance_without_type() -> None:
    with pytest.raises(ValueError, match="type must be one of"):
        parse_config({"adapters": {"pedalboard": {"enabled": True}}})


def test_parse_config_rejects_additional_gpio_instances() -> None:
    with pytest.raises(ValueError, match="cannot create additional gpio instances"):
        parse_config({"adapters": {"gpio_extra": {"type": "gpio", "enabled": True}}})


def test_parse_config_rejects_mismatched_default_adapter_type() -> None:
    with pytest.raises(ValueError, match="default adapter table"):
        parse_config({"adapters": {"osc": {"type": "usb_midi", "enabled": True}}})


def test_parse_config_rejects_adapter_names_that_break_mapping_prefixes() -> None:
    with pytest.raises(ValueError, match="cannot contain"):
        parse_config({"adapters": {"osc:bad": {"type": "osc", "enabled": True}}})
