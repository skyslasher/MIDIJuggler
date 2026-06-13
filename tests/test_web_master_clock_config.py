import asyncio
from pathlib import Path

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_master_clock_config_payload_lists_midi_output_targets() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 120.0,
                "output_targets": ["midi"],
            },
            "adapters": {
                "midi": {"enabled": True},
                "rtp_remote": {
                    "type": "rtp_midi",
                    "enabled": False,
                },
                "osc": {"enabled": True},
            },
        }
    )
    bus = EventBus()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
    )

    payload = interface.master_clock_config_payload()

    assert payload["enabled"] is True
    assert payload["bpm"] == 120.0
    assert "click_command" not in payload
    assert payload["available_audio_devices"][0] == {
        "id": "",
        "label": "default (software/mixed)",
        "mode": "alias",
    }
    assert [
        (target["name"], target["type"], target["selected"])
        for target in payload["available_output_targets"]
    ] == [
        ("midi", "midi", True),
        ("rtp_midi", "rtp_midi", False),
        ("rtp_remote", "rtp_midi", False),
    ]
    assert "midi_input_targets" not in payload
    assert "osc_input_targets" not in payload
    assert "midi_channel" not in payload


def test_apply_master_clock_config_persists_section(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [master_clock]
        enabled = false
        bpm = 120.0

        [adapters.midi]
        enabled = true
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    bus = EventBus()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_master_clock_config(
            {
                "enabled": True,
                "bpm": 128.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "output_targets": ["midi"],
                "click_interval": "eighth",
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert result["enabled"] is True
    assert saved.master_clock.bpm == pytest.approx(128.0)
    assert saved.master_clock.output_targets == ["midi"]
    assert saved.master_clock.click_interval == "eighth"
    assert saved.master_clock.click_command == "aplay"


def test_apply_master_clock_config_updates_alsa_dmix_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[master_clock]\nbpm = 120.0\n", encoding="utf-8")
    config = load_config(config_file)
    bus = EventBus()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        config_path=config_file,
        alsa_config_path=tmp_path / "asoundrc",
    )

    result = asyncio.run(
        interface.apply_master_clock_config(
            {
                "enabled": True,
                "bpm": 120.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "output_targets": [],
                "click_audio_device": "plughw:1,0",
            }
        )
    )

    assert result["alsa_config_error"] == ""
    assert 'pcm "hw:1,0"' in (tmp_path / "asoundrc").read_text(encoding="utf-8")


def test_apply_master_clock_config_keeps_runtime_change_when_persisting_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[master_clock]\nenabled = false\n", encoding="utf-8")
    config = load_config(config_file)
    bus = EventBus()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        config_path=config_file,
    )

    def deny_persist(path: str | Path, config: object, **kwargs: object) -> None:
        raise PermissionError(13, "Permission denied", f"{path}.tmp")

    monkeypatch.setattr("midijuggler.web.server.save_master_clock_config", deny_persist)

    result = asyncio.run(
        interface.apply_master_clock_config(
            {
                "enabled": True,
                "bpm": 99.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "output_targets": [],
            }
        )
    )

    assert result["persisted"] is False
    assert "Permission denied" in result["persist_error"]
    assert interface.master_clock.bpm == pytest.approx(99.0)


def test_apply_master_clock_config_rejects_unknown_output_target() -> None:
    config = parse_config({"adapters": {"midi": {"enabled": True}}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="unknown MIDI clock output targets"):
        asyncio.run(
            interface.apply_master_clock_config({"output_targets": ["missing"]})
        )


def test_apply_master_clock_config_clears_legacy_inputs_with_datapoint_routing(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [runtime]
        datapoint_routing = true

        [master_clock]
        enabled = true
        midi_input_targets = ["midi"]
        osc_input_targets = ["osc"]

        [adapters.midi]
        enabled = true

        [adapters.osc]
        enabled = true
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_master_clock_config(
            {
                "enabled": True,
                "bpm": 120.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "output_targets": [],
            }
        )
    )

    saved = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert result["enabled"] is True
    assert interface.master_clock.config.midi_input_targets == []
    assert interface.master_clock.config.osc_input_targets == []
    assert saved.master_clock.midi_input_targets is None
    assert saved.master_clock.osc_input_targets is None
    assert "midi_input_targets" not in saved_text
    assert "bpm_msb_cc" not in saved_text


def test_apply_master_clock_config_persists_input_targets_without_datapoint_routing(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [master_clock]
        enabled = true

        [adapters.midi]
        enabled = true

        [adapters.osc]
        enabled = true
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_master_clock_config(
            {
                "enabled": True,
                "bpm": 120.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "output_targets": [],
                "midi_input_targets": ["midi"],
                "osc_input_targets": ["osc"],
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert saved.master_clock.midi_input_targets == ["midi"]
    assert saved.master_clock.osc_input_targets == ["osc"]


def test_apply_master_clock_config_rejects_unknown_input_target() -> None:
    config = parse_config(
        {
            "adapters": {
                "midi": {"enabled": True},
                "osc": {"enabled": True},
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="unknown master clock midi_input_targets"):
        asyncio.run(
            interface.apply_master_clock_config({"midi_input_targets": ["missing"]})
        )


def test_apply_master_clock_config_rejects_disabled_output_target() -> None:
    config = parse_config(
        {
            "adapters": {
                "midi": {"enabled": True},
                "rtp_midi": {"enabled": False},
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="unknown MIDI clock output targets"):
        asyncio.run(
            interface.apply_master_clock_config({"output_targets": ["rtp_midi"]})
        )


def test_export_and_import_config_text(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [web]
        port = 8080

        [adapters.gpio]
        enabled = true
        pins = [17]
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    exported = interface.export_config_text()
    result = interface.import_config_text(
        """
        [web]
        port = 9090

        [adapters.gpio]
        enabled = true
        pins = [22]
        """
    )

    saved = load_config(config_file)

    assert "[adapters.gpio]" in exported
    assert result == {"imported": True, "restart_required": True}
    assert saved.web.port == 9090
    assert saved.adapters["gpio"].options["pins"] == [22]


def test_import_config_text_rejects_invalid_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[web]\nport = 8080\n", encoding="utf-8")
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    with pytest.raises(Exception):
        interface.import_config_text("[web\n")


def test_tap_tempo_updates_master_clock_bpm() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 100.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
            }
        }
    )
    bus = EventBus()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
    )

    asyncio.run(interface.apply_tap_tempo(timestamp=10.0))
    result = asyncio.run(interface.apply_tap_tempo(timestamp=10.497))

    assert result["master_clock"]["bpm"] == pytest.approx(120.5)
    assert interface.master_clock.config.bpm == pytest.approx(120.5)


def test_master_clock_transport_toggle_starts_and_stops() -> None:
    config = parse_config({"master_clock": {"enabled": True}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    started = asyncio.run(interface.apply_master_clock_transport("toggle"))
    stopped = asyncio.run(interface.apply_master_clock_transport("toggle"))

    assert started["master_clock"]["running"] is True
    assert stopped["master_clock"]["running"] is False
