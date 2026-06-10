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
                "output_targets": ["usb_midi"],
            },
            "adapters": {
                "usb_midi": {"enabled": True},
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
    assert payload["available_audio_devices"][0] == {"id": "", "label": "default"}
    assert [
        (target["name"], target["type"], target["selected"])
        for target in payload["available_output_targets"]
    ] == [
        ("usb_midi", "usb_midi", True),
        ("rtp_midi", "rtp_midi", False),
        ("rtp_remote", "rtp_midi", False),
    ]


def test_apply_master_clock_config_persists_section(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [master_clock]
        enabled = false
        bpm = 120.0

        [adapters.usb_midi]
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
                "output_targets": ["usb_midi"],
                "click_interval": "eighth",
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert result["enabled"] is True
    assert saved.master_clock.bpm == pytest.approx(128.0)
    assert saved.master_clock.output_targets == ["usb_midi"]
    assert saved.master_clock.click_interval == "eighth"
    assert saved.master_clock.click_command == "aplay"


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

    def deny_persist(path: str | Path, config: object) -> None:
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
    config = parse_config({"adapters": {"usb_midi": {"enabled": True}}})
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


def test_apply_master_clock_config_rejects_disabled_output_target() -> None:
    config = parse_config(
        {
            "adapters": {
                "usb_midi": {"enabled": True},
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
    result = asyncio.run(interface.apply_tap_tempo(timestamp=10.5))

    assert result["master_clock"]["bpm"] == pytest.approx(120.0)
    assert interface.master_clock.config.bpm == pytest.approx(120.0)


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
