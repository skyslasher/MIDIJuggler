import asyncio
from pathlib import Path

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AdapterConfig, load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.rtp_midi.discovery import RtpMidiSession, local_mdns_server_name, rtp_session_id
from midijuggler.rtp_midi.manager import RtpMidiManager
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
                "midi": {
                    "enabled": True,
                    "input_port": "MIDIJuggler In",
                    "output_port": "MIDIJuggler Out",
                },
                "usb_stage": {
                    "type": "midi",
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
        "midi",
        "rtp_midi",
        "usb_stage",
    ]
    midi_instance = next(
        instance for instance in payload["instances"] if instance["name"] == "midi"
    )
    rtp_instance = next(
        instance for instance in payload["instances"] if instance["name"] == "rtp_midi"
    )
    assert midi_instance["input_port"] == "MIDIJuggler In"
    assert rtp_instance["role"] == "host"
    assert rtp_instance["session_name"] == "MIDIJuggler"
    assert rtp_instance["port"] == 5004
    assert payload["available_midi_libraries"]
    assert "rtp_midi_available" in payload
    assert "discovered_rtp_sessions" in payload


def test_apply_midi_adapters_config_persists_sections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
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
                        "name": "midi",
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
    assert saved.adapters["midi"].options["input_port"] == "MIDIJuggler In"
    assert saved.adapters["rtp_midi"].enabled is True
    assert saved.adapters["rtp_midi"].options["port"] == 5005
    assert 'input_port = "MIDIJuggler In"' in saved_text
    assert 'session_name = "MIDIJuggler"' in saved_text


def test_apply_midi_adapters_config_persists_listen_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.rtp_midi]
        enabled = false
        role = "host"
        session_name = "MIDIJuggler"
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
                        "name": "rtp_midi",
                        "enabled": True,
                        "role": "listen",
                        "session_name": "Local Only",
                        "port": 5006,
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert saved.adapters["rtp_midi"].options["role"] == "listen"
    assert saved.adapters["rtp_midi"].options["session_name"] == "Local Only"
    assert saved.adapters["rtp_midi"].options["port"] == 5006


def test_apply_midi_adapters_config_keeps_runtime_change_when_persisting_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.midi]
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
                        "name": "midi",
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
    assert config.adapters["midi"].options["input_port"] == "New In"


def test_join_mode_excludes_locally_hosted_rtp_sessions(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    manager = RtpMidiManager()
    local_host = local_mdns_server_name()
    local_id = rtp_session_id("MIDIJuggler", local_host, 5004)
    remote_id = rtp_session_id("MacSession", "MacBook.local.", 5004)
    manager._discovery = manager._discovery or None
    from midijuggler.rtp_midi.discovery import RtpMidiDiscovery

    discovery = RtpMidiDiscovery()
    discovery._sessions = {
        local_id: RtpMidiSession(
            id=local_id,
            name="MIDIJuggler",
            host=local_host,
            port=5004,
        ),
        remote_id: RtpMidiSession(
            id=remote_id,
            name="MacSession",
            host="MacBook.local.",
            port=5004,
        ),
    }
    manager._discovery = discovery
    manager._instances["rtp_midi"] = AdapterConfig(
        enabled=True,
        kind="rtp_midi",
        options={"role": "host", "session_name": "MIDIJuggler", "port": 5004},
    )
    manager._announcers["rtp_midi"] = object()

    config = parse_config(
        {
            "adapters": {
                "rtp_midi": {
                    "enabled": True,
                    "role": "join",
                    "join_target": remote_id,
                    "port": 5004,
                }
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        rtp_midi_manager=manager,
    )

    payload = interface.midi_adapters_config_payload()
    rtp_instance = next(
        instance for instance in payload["instances"] if instance["name"] == "rtp_midi"
    )
    join_choices = rtp_instance["available_rtp_sessions"]

    assert [choice["id"] for choice in join_choices] == [remote_id]
    assert [session["id"] for session in payload["joinable_rtp_sessions"]] == [remote_id]
    assert local_id in payload["hosted_rtp_session_ids"]


def test_apply_midi_adapters_config_creates_midi_instance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.midi]
        enabled = false
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
                "kind": "midi",
                "instances": [
                    {
                        "name": "stage_midi",
                        "type": "midi",
                        "enabled": True,
                        "input_port": "Stage In",
                        "output_port": "Stage Out",
                    }
                ],
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert saved.adapters["stage_midi"].enabled is True
    assert saved.adapters["stage_midi"].kind == "midi"
    assert saved.adapters["stage_midi"].options["input_port"] == "Stage In"
    assert "[adapters.stage_midi]" in config_file.read_text(encoding="utf-8")


def test_apply_midi_adapters_config_deletes_additional_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
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
                "kind": "midi",
                "instances": [
                    {
                        "name": "midi",
                        "enabled": True,
                        "input_port": "",
                        "output_port": "",
                    }
                ],
                "deleted": ["stage_midi"],
            }
        )
    )

    saved = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert result["persisted"] is True
    assert "stage_midi" not in saved.adapters
    assert "[adapters.stage_midi]" not in saved_text


def test_apply_midi_adapters_config_rejects_deleting_default_instance() -> None:
    config = parse_config({"adapters": {"midi": {"enabled": True}}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="cannot delete default adapter instance"):
        asyncio.run(
            interface.apply_midi_adapters_config(
                {
                    "kind": "midi",
                    "instances": [{"name": "midi", "enabled": True}],
                    "deleted": ["midi"],
                }
            )
        )


def test_apply_midi_adapters_config_rejects_unknown_instance() -> None:
    config = parse_config({"adapters": {"midi": {"enabled": True}}})
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
