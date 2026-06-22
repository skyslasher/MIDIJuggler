import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AdapterConfig, load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.rtp_midi.discovery import RtpMidiSession, local_mdns_server_name, rtp_session_id
from midijuggler.rtp_midi.manager import RtpMidiManager
from midijuggler.events import AdapterStatusEvent
from midijuggler.web.server import WebInterface


def _mock_midi_ports(monkeypatch: pytest.MonkeyPatch, ports: list[dict[str, str]]) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: ports)
    monkeypatch.setattr("midijuggler.web.server.list_midi_input_ports", lambda: ports)
    monkeypatch.setattr("midijuggler.web.server.list_midi_output_ports", lambda: ports)


def test_midi_adapters_config_payload_lists_instances(monkeypatch) -> None:
    _mock_midi_ports(
        monkeypatch,
        [
            {
                "id": "MIDIJuggler In",
                "address": "20:0",
                "label": "MIDIJuggler / MIDIJuggler In (20:0)",
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


def test_midi_adapters_config_payload_includes_echo_guard_ms(monkeypatch) -> None:
    _mock_midi_ports(monkeypatch, [])
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "echo_guard_ms": 45,
                }
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
    instance = next(
        item for item in payload["instances"] if item["name"] == "xtouch_mini"
    )

    assert instance["echo_guard_ms"] == 45


def test_apply_midi_adapters_config_persists_echo_guard_ms(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _mock_midi_ports(monkeypatch, [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.midi]
        enabled = true
        type = "midi"
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
                        "echo_guard_ms": 0,
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert saved.adapters["midi"].options["echo_guard_ms"] == 0


def test_midi_adapters_config_payload_includes_feedback_refresh_interval(monkeypatch) -> None:
    _mock_midi_ports(monkeypatch, [])
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                    "feedback_refresh_interval": 1.5,
                }
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
    instance = next(
        item for item in payload["instances"] if item["name"] == "xtouch_mini"
    )

    assert instance["feedback_refresh_interval"] == 1.5


def test_apply_midi_adapters_config_persists_feedback_refresh_interval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _mock_midi_ports(monkeypatch, [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.xtouch_mini]
        enabled = true
        type = "midi"
        midi_library = "behringer_xtouch_mini"
        feedback_refresh_interval = 0
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
                        "name": "xtouch_mini",
                        "enabled": True,
                        "midi_library": "behringer_xtouch_mini",
                        "feedback_refresh_interval": 2.0,
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert saved.adapters["xtouch_mini"].options["feedback_refresh_interval"] == 2.0


def test_apply_midi_adapters_config_rejects_feedback_refresh_for_other_libraries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _mock_midi_ports(monkeypatch, [])
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.midi]
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

    with pytest.raises(ValueError, match="behringer_xtouch_mini"):
        asyncio.run(
            interface.apply_midi_adapters_config(
                {
                    "instances": [
                        {
                            "name": "midi",
                            "enabled": True,
                            "feedback_refresh_interval": 1.0,
                        }
                    ]
                }
            )
        )


def test_apply_midi_adapters_config_persists_sections(tmp_path: Path, monkeypatch) -> None:
    _mock_midi_ports(monkeypatch, [])
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


def test_apply_midi_adapters_config_migrates_legacy_port_address(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = [
        {
            "id": "X-TOUCH MINI",
            "address": "24:0",
            "label": "X-TOUCHMINI / X-TOUCH MINI (24:0)",
            "client": "X-TOUCHMINI",
        }
    ]
    _mock_midi_ports(monkeypatch, ports)
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.midi]
        enabled = true
        input_port = "24:0"
        output_port = "24:0"
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
                        "input_port": "24:0",
                        "output_port": "24:0",
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)
    midi = next(item for item in result["instances"] if item["name"] == "midi")
    assert midi["input_port"] == "X-TOUCH MINI"
    assert midi["output_port"] == "X-TOUCH MINI"
    assert saved.adapters["midi"].options["input_port"] == "X-TOUCH MINI"
    assert 'input_port = "24:0"' not in config_file.read_text(encoding="utf-8")


def test_apply_midi_adapters_config_persists_listen_mode(tmp_path: Path, monkeypatch) -> None:
    _mock_midi_ports(monkeypatch, [])
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
    _mock_midi_ports(monkeypatch, [])
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
    _mock_midi_ports(monkeypatch, [])
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
    _mock_midi_ports(monkeypatch, [])
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


def test_apply_midi_adapters_config_starts_created_midi_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_midi_ports(monkeypatch, [])
    start_mock = AsyncMock()
    monkeypatch.setattr(MidiAdapter, "start", start_mock)

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
        runtime_adapters=[],
    )

    asyncio.run(
        interface.apply_midi_adapters_config(
            {
                "kind": "midi",
                "instances": [
                    {
                        "name": "xtouch_mini",
                        "type": "midi",
                        "enabled": True,
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    }
                ],
            }
        )
    )

    assert "xtouch_mini" in interface.midi_adapters
    start_mock.assert_awaited()


def test_apply_midi_adapters_config_stops_deleted_midi_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_midi_ports(monkeypatch, [])
    stop_mock = AsyncMock()
    monkeypatch.setattr(MidiAdapter, "stop", stop_mock)
    monkeypatch.setattr(MidiAdapter, "start", AsyncMock())

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
    bus = EventBus()
    stage_adapter = MidiAdapter(
        "stage_midi",
        config.adapters["stage_midi"],
        bus,
        app_config=config,
    )
    stage_adapter.running = True
    runtime_adapters = [stage_adapter]
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        midi_adapters={"stage_midi": stage_adapter},
        config_path=config_file,
        runtime_adapters=runtime_adapters,
    )

    asyncio.run(
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

    assert "stage_midi" not in interface.midi_adapters
    stop_mock.assert_awaited()
    assert stage_adapter not in runtime_adapters


def test_apply_midi_adapters_config_deletes_additional_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_midi_ports(monkeypatch, [])
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


def test_apply_midi_adapters_config_can_rename_instance(tmp_path: Path, monkeypatch) -> None:
    _mock_midi_ports(monkeypatch, [])
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
                        "name": "foh_midi",
                        "previous_name": "stage_midi",
                        "enabled": True,
                        "input_port": "FOH In",
                        "output_port": "FOH Out",
                    }
                ],
            }
        )
    )

    saved = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert result["persisted"] is True
    assert "stage_midi" not in saved.adapters
    assert saved.adapters["foh_midi"].options["input_port"] == "FOH In"
    assert "[adapters.foh_midi]" in saved_text
    assert "[adapters.stage_midi]" not in saved_text


def test_apply_midi_adapters_config_rejects_default_rename() -> None:
    config = parse_config({"adapters": {"midi": {"enabled": True}}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="cannot rename default adapter instance"):
        asyncio.run(
            interface.apply_midi_adapters_config(
                {
                    "instances": [
                        {
                            "name": "foh_midi",
                            "previous_name": "midi",
                            "enabled": True,
                        }
                    ]
                }
            )
        )


def test_web_interface_exposes_cached_adapter_runtime_status() -> None:
    async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
        config = parse_config(
            {
                "adapters": {
                    "midi": {
                        "enabled": True,
                        "input_port": "MIDIJuggler In",
                    }
                }
            }
        )
        interface = WebInterface(
            config,
            EventBus(),
            ClockBpmTracker(),
            MasterClock(config.master_clock, EventBus()),
        )
        await interface._broadcast_event(
            AdapterStatusEvent(
                source="midi",
                adapter="midi",
                status="started",
                detail="MIDI adapter waiting for input MIDIJuggler In",
                connection_phase="waiting",
            )
        )
        return interface._status_payload(), interface.midi_adapters_config_payload()

    status_payload, midi_payload = asyncio.run(scenario())

    runtime = {
        "status": "started",
        "detail": "MIDI adapter waiting for input MIDIJuggler In",
        "connection_phase": "waiting",
    }
    assert status_payload["adapters"]["midi"]["runtime_connection"] == runtime
    assert midi_payload["instances"][0]["runtime_connection"] == runtime
