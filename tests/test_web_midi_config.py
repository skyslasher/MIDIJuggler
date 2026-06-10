import asyncio
from pathlib import Path

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_midi_adapters_config_payload_lists_instances(monkeypatch) -> None:
    monkeypatch.setattr(
        "midijuggler.web.server.list_midi_ports",
        lambda: [
            {
                "id": "MIDIJuggler In",
                "label": "MIDIJuggler / MIDIJuggler In",
                "client": "MIDIJuggler",
            }
        ],
    )
    config = parse_config(
        {
            "adapters": {
                "usb_midi": {
                    "enabled": True,
                    "input_port": "MIDIJuggler In",
                    "output_port": "MIDIJuggler Out",
                },
                "usb_stage": {
                    "type": "usb_midi",
                    "enabled": False,
                    "input_port": "Stage MIDI In",
                    "output_port": "Stage MIDI Out",
                },
                "rtp_midi": {
                    "enabled": True,
                    "role": "host",
                    "session_name": "MIDIJuggler",
                    "port": 5004,
                },
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

    payload = interface.midi_adapters_config_payload()

    assert [instance["name"] for instance in payload["instances"]] == [
        "rtp_midi",
        "usb_midi",
        "usb_stage",
    ]
    assert payload["instances"][1]["input_port"] == "MIDIJuggler In"
    assert payload["instances"][0]["role"] == "host"
    assert payload["instances"][0]["session_name"] == "MIDIJuggler"
    assert payload["instances"][0]["port"] == 5004
    assert payload["available_midi_libraries"]
    assert "rtp_midi_available" in payload
    assert "discovered_rtp_sessions" in payload


def test_apply_midi_adapters_config_persists_sections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.usb_midi]
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
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_midi_adapters_config(
            {
                "instances": [
                    {
                        "name": "usb_midi",
                        "enabled": True,
                        "input_port": "MIDIJuggler In",
                        "output_port": "MIDIJuggler Out",
                    },
                    {
                        "name": "rtp_midi",
                        "enabled": True,
                        "role": "host",
                        "session_name": "MIDIJuggler",
                        "port": 5005,
                    },
                ]
            }
        )
    )

    saved = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert result["persisted"] is True
    assert saved.adapters["usb_midi"].options["input_port"] == "MIDIJuggler In"
    assert saved.adapters["rtp_midi"].enabled is True
    assert saved.adapters["rtp_midi"].options["port"] == 5005
    assert 'input_port = "MIDIJuggler In"' in saved_text
    assert 'session_name = "MIDIJuggler"' in saved_text


def test_apply_midi_adapters_config_keeps_runtime_change_when_persisting_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.usb_midi]
        enabled = true
        input_port = "Old In"
        output_port = "Old Out"
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

    def deny_persist(path: str | Path, instances: object) -> None:
        raise PermissionError(13, "Permission denied", f"{path}.tmp")

    monkeypatch.setattr("midijuggler.web.server.save_midi_adapter_configs", deny_persist)

    result = asyncio.run(
        interface.apply_midi_adapters_config(
            {
                "instances": [
                    {
                        "name": "usb_midi",
                        "enabled": True,
                        "input_port": "New In",
                        "output_port": "New Out",
                    }
                ]
            }
        )
    )

    assert result["persisted"] is False
    assert "Permission denied" in result["persist_error"]
    assert config.adapters["usb_midi"].options["input_port"] == "New In"


def test_apply_midi_adapters_config_rejects_unknown_instance() -> None:
    config = parse_config({"adapters": {"usb_midi": {"enabled": True}}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="unknown MIDI adapter instance"):
        asyncio.run(
            interface.apply_midi_adapters_config(
                {"instances": [{"name": "missing", "enabled": True}]}
            )
        )
