from pathlib import Path

import pytest

from midijuggler.config import (
    remove_midi_adapter_configs,
    AdapterConfig,
    MasterClockConfig,
    load_config,
    parse_config,
    save_gpio_adapter_options,
    save_master_clock_config,
    save_midi_adapter_configs,
)


def test_parse_config_reads_web_adapters_and_connections() -> None:
    config = parse_config(
        {
            "web": {"host": "127.0.0.1", "port": 9090},
            "master_clock": {
                "enabled": True,
                "bpm": 118.5,
                "output_targets": ["midi", "rtp_midi"],
                "click_interval": "eighth",
            },
            "adapters": {
                "gpio": {"enabled": True, "pins": [17]},
                "midi": {"enabled": True},
            },
            "devices": [
                {"id": "gpio", "adapter": "gpio", "library_kind": "gpio"},
                {"id": "midi", "adapter": "midi", "library_kind": "midi"},
            ],
            "connections": [
                {
                    "id": "switch",
                    "source": "gpio.pin17",
                    "target": "midi.cc_1_64",
                    "invert": True,
                }
            ],
        }
    )

    assert config.web.host == "127.0.0.1"
    assert config.web.port == 9090
    assert config.master_clock.enabled is True
    assert config.master_clock.bpm == 118.5
    assert config.master_clock.output_targets == ["midi", "rtp_midi"]
    assert config.master_clock.click_interval == "eighth"
    assert config.adapters["gpio"].enabled is True
    assert config.adapters["gpio"].kind == "gpio"
    assert config.adapters["gpio"].options["pins"] == [17]
    assert config.adapters["osc"].enabled is False
    assert config.connections[0].id == "switch"
    assert config.connections[0].invert is True


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
                    "type": "midi",
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
    assert config.adapters["usb_stage"].kind == "midi"
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

        [adapters.midi]
        enabled = true

        [[devices]]
        id = "osc"
        adapter = "osc"
        library_kind = "osc"

        [[devices]]
        id = "midi"
        adapter = "midi"
        library_kind = "midi"

        [[connections]]
        id = "pedal"
        source = "osc.pedal"
        target = "midi.cc_1_11"
        modifier = "range_map"
        input_min = 0.0
        input_max = 1.0
        output_min = 0.0
        output_max = 127.0
        invert = false
        """,
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.web.port == 8081
    assert config.connections[0].target == "midi.cc_1_11"


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


def test_remove_midi_adapter_configs_deletes_adapter_sections(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.midi]
        enabled = true

        [adapters.stage_midi]
        type = "midi"
        enabled = true
        input_port = "Stage In"
        output_port = "Stage Out"
        """,
        encoding="utf-8",
    )

    remove_midi_adapter_configs(config_file, ["stage_midi"])

    saved_text = config_file.read_text(encoding="utf-8")
    config = load_config(config_file)

    assert "stage_midi" not in config.adapters
    assert "[adapters.stage_midi]" not in saved_text
    assert "[adapters.midi]" in saved_text


def test_save_midi_adapter_configs_replaces_adapter_sections(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.midi]
        enabled = true
        input_port = "Old In"
        output_port = "Old Out"

        [adapters.rtp_midi]
        enabled = false
        session_name = "Old Session"
        port = 5004
        """,
        encoding="utf-8",
    )

    save_midi_adapter_configs(
        config_file,
        {
            "midi": AdapterConfig(
                enabled=True,
                options={
                    "input_port": "MIDIJuggler In",
                    "output_port": "MIDIJuggler Out",
                },
                kind="midi",
            ),
            "rtp_remote": AdapterConfig(
                enabled=True,
                options={"session_name": "Remote", "port": 5005},
                kind="rtp_midi",
            ),
        },
    )

    config = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert config.adapters["midi"].options["input_port"] == "MIDIJuggler In"
    assert config.adapters["rtp_remote"].enabled is True
    assert config.adapters["rtp_remote"].options["port"] == 5005
    assert "[adapters.rtp_remote]" in saved_text
    assert 'type = "rtp_midi"' in saved_text


def test_parse_config_reads_master_clock_input_targets() -> None:
    config = parse_config(
        {
            "master_clock": {
                "midi_input_targets": ["midi"],
                "osc_input_targets": ["osc", "osc_pedalboard"],
            }
        }
    )

    assert config.master_clock.midi_input_targets == ["midi"]
    assert config.master_clock.osc_input_targets == ["osc", "osc_pedalboard"]


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
            output_targets=["midi", "rtp_midi"],
            midi_input_targets=["midi"],
            osc_input_targets=["osc"],
            click_enabled=True,
            click_interval="half",
            click_wav="/etc/midijuggler/click.wav",
        ),
    )

    config = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert config.master_clock.enabled is True
    assert config.master_clock.bpm == pytest.approx(128.5)
    assert config.master_clock.output_targets == ["midi", "rtp_midi"]
    assert config.master_clock.click_interval == "half"
    assert 'output_targets = ["midi", "rtp_midi"]' in saved_text
    assert 'midi_input_targets = ["midi"]' in saved_text
    assert 'osc_input_targets = ["osc"]' in saved_text
    assert "click_command" not in saved_text
    saved_lines = saved_text.splitlines()
    click_device_index = saved_lines.index('click_audio_device = ""')
    assert saved_lines[click_device_index + 1] == 'name = "Master clock"'
    assert saved_lines[click_device_index + 2] == "beat_flash_ms = 120.0"
    assert saved_lines[click_device_index + 3] == ""
    assert saved_lines[click_device_index + 4].strip() == "[adapters.gpio]"


def test_parse_config_rejects_mappings_section() -> None:
    with pytest.raises(ValueError, match="mappings"):
        parse_config(
            {
                "mappings": [
                    {"id": "broken", "source": "gpio:pin17", "target": "midi:cc:1:64"}
                ]
            }
        )


def test_parse_config_rejects_incomplete_connection() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        parse_config(
            {
                "connections": [{"id": "broken", "source": "gpio.pin17"}],
            }
        )


def test_parse_config_rejects_invalid_master_clock_interval() -> None:
    with pytest.raises(ValueError, match="click_interval"):
        parse_config({"master_clock": {"click_interval": "triplet"}})


def test_parse_config_reads_tap_tempo_min_taps() -> None:
    config = parse_config({"master_clock": {"tap_tempo_min_taps": 3}})
    assert config.master_clock.tap_tempo_min_taps == 3


def test_parse_config_reads_bpm_step_and_quantize() -> None:
    config = parse_config(
        {"master_clock": {"bpm_step": 1.0, "bpm_huge_step": 10.0, "bpm_quantize": 1.0}}
    )
    assert config.master_clock.bpm_step == pytest.approx(1.0)
    assert config.master_clock.bpm_huge_step == pytest.approx(10.0)
    assert config.master_clock.bpm_quantize == pytest.approx(1.0)


def test_parse_config_rejects_invalid_bpm_quantize() -> None:
    with pytest.raises(ValueError, match="bpm_quantize"):
        parse_config({"master_clock": {"bpm_quantize": 0.25}})


def test_parse_config_rejects_fractional_bpm_quantize() -> None:
    with pytest.raises(ValueError, match="bpm_quantize"):
        parse_config({"master_clock": {"bpm_quantize": 0.5}})


def test_parse_config_rejects_invalid_bpm_step() -> None:
    with pytest.raises(ValueError, match="bpm_step"):
        parse_config({"master_clock": {"bpm_step": 0}})


def test_parse_config_rejects_tap_tempo_min_taps_below_minimum() -> None:
    with pytest.raises(ValueError, match="tap_tempo_min_taps"):
        parse_config({"master_clock": {"tap_tempo_min_taps": 2}})


def test_parse_config_rejects_unknown_adapter_instance_without_type() -> None:
    with pytest.raises(ValueError, match="type must be one of"):
        parse_config({"adapters": {"pedalboard": {"enabled": True}}})


def test_parse_config_rejects_additional_gpio_instances() -> None:
    with pytest.raises(ValueError, match="cannot create additional gpio instances"):
        parse_config({"adapters": {"gpio_extra": {"type": "gpio", "enabled": True}}})


def test_parse_config_migrates_legacy_usb_midi_adapter_tables() -> None:
    config = parse_config(
        {
            "master_clock": {
                "output_targets": ["midi"],
                "midi_input_targets": ["midi"],
            },
            "adapters": {
                "usb_midi": {
                    "enabled": True,
                    "input_port": "MIDIJuggler In",
                    "output_port": "MIDIJuggler Out",
                },
                "usb_stage": {
                    "type": "usb_midi",
                    "enabled": False,
                },
                "gpio": {"enabled": True, "pins": [17]},
            },
            "devices": [
                {"id": "midi", "adapter": "midi", "library_kind": "midi"},
                {"id": "usb_stage", "adapter": "usb_stage", "library_kind": "midi"},
                {"id": "gpio", "adapter": "gpio", "library_kind": "gpio"},
            ],
            "connections": [
                {
                    "id": "legacy-target",
                    "source": "gpio.pin17",
                    "target": "midi.cc_1_64",
                }
            ],
        }
    )

    assert config.adapters["midi"].enabled is True
    assert config.adapters["midi"].kind == "midi"
    assert "usb_midi" not in config.adapters
    assert config.adapters["usb_stage"].kind == "midi"
    assert config.master_clock.output_targets == ["midi"]
    assert config.master_clock.midi_input_targets == ["midi"]
    assert config.connections[0].target == "midi.cc_1_64"


def test_parse_config_rejects_mismatched_default_adapter_type() -> None:
    with pytest.raises(ValueError, match="default adapter table"):
        parse_config({"adapters": {"osc": {"type": "midi", "enabled": True}}})


def test_parse_config_rejects_adapter_names_that_break_mapping_prefixes() -> None:
    with pytest.raises(ValueError, match="cannot contain"):
        parse_config({"adapters": {"osc:bad": {"type": "osc", "enabled": True}}})
