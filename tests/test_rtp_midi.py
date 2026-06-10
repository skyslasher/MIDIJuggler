import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from midijuggler.config import AdapterConfig, parse_config
from midijuggler.clock import ClockBpmTracker
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.rtp_midi.discovery import (
    APPLE_MIDI_SERVICE_TYPE,
    RtpMidiDiscovery,
    RtpMidiSession,
    _RtpMidiServiceListener,
    build_apple_midi_service_name,
    local_mdns_server_name,
    parse_rtp_session_name,
    rtp_session_id,
)
from midijuggler.rtp_midi.manager import RtpMidiManager
from midijuggler.web.server import WebInterface


def test_parse_rtp_session_name_strips_service_suffix() -> None:
    service_name = f"Studio Session@MyMac.{APPLE_MIDI_SERVICE_TYPE}"
    assert parse_rtp_session_name(service_name) == "Studio Session"


def test_rtp_session_id_is_stable() -> None:
    assert rtp_session_id("Studio", "pi.local.", 5004) == "pi.local.:5004:Studio"


def test_build_apple_midi_service_name_uses_service_type_suffix() -> None:
    assert (
        build_apple_midi_service_name("MIDIJuggler")
        == f"MIDIJuggler.{APPLE_MIDI_SERVICE_TYPE}"
    )


def test_local_mdns_server_name_ends_with_local() -> None:
    assert local_mdns_server_name().endswith(".local.")


def test_service_listener_uses_sync_get_service_info() -> None:
    discovery = RtpMidiDiscovery()
    listener = _RtpMidiServiceListener(discovery)
    service_name = f"Studio@{local_mdns_server_name().removesuffix('.')}.{APPLE_MIDI_SERVICE_TYPE}"

    class FakeInfo:
        server = "pi.local."
        port = 5004
        addresses = [b"\xc0\xa8\x01\n"]

    class FakeZeroconf:
        def get_service_info(self, type_: str, name: str, timeout: int = 3000):
            assert type_ == APPLE_MIDI_SERVICE_TYPE
            assert name == service_name
            assert timeout == 3000
            return FakeInfo()

    listener.add_service(FakeZeroconf(), APPLE_MIDI_SERVICE_TYPE, service_name)

    sessions = discovery.sessions()
    assert len(sessions) == 1
    assert sessions[0].name == "Studio"
    assert sessions[0].port == 5004


def test_rtp_session_as_dict_includes_label() -> None:
    session = RtpMidiSession(
        id="pi.local.:5004:Studio",
        name="Studio",
        host="pi.local.",
        port=5004,
        addresses=("192.168.1.10",),
    )

    assert session.as_dict()["label"] == "Studio (pi.local.:5004)"


def test_rtp_midi_manager_hosts_enabled_instance(monkeypatch) -> None:
    monkeypatch.setattr(
        "midijuggler.rtp_midi.manager.zeroconf_available",
        lambda: True,
    )
    announcer = MagicMock()
    announcer.start = AsyncMock()
    announcer.stop = AsyncMock()
    monkeypatch.setattr(
        "midijuggler.rtp_midi.manager.RtpMidiAnnouncer",
        lambda session_name, port, zeroconf: announcer,
    )
    shared_zeroconf = MagicMock()
    shared_zeroconf.async_close = AsyncMock()
    monkeypatch.setattr(
        "zeroconf.asyncio.AsyncZeroconf",
        lambda: shared_zeroconf,
    )
    discovery = MagicMock()
    discovery.start = AsyncMock()
    discovery.stop = AsyncMock()
    discovery.sessions = MagicMock(return_value=[])
    monkeypatch.setattr(
        "midijuggler.rtp_midi.manager.RtpMidiDiscovery",
        lambda: discovery,
    )

    async def exercise() -> None:
        manager = RtpMidiManager()
        await manager.start()
        await manager.apply_instance(
            "rtp_midi",
            AdapterConfig(
                enabled=True,
                kind="rtp_midi",
                options={"role": "host", "session_name": "MIDIJuggler", "port": 5004},
            ),
        )
        announcer.start.assert_awaited_once()
        await manager.stop()
        announcer.stop.assert_awaited_once()

    asyncio.run(exercise())


def test_midi_payload_includes_rtp_discovery_fields(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    manager = RtpMidiManager()
    manager._discovery._sessions["studio"] = RtpMidiSession(
        id="mac.local.:5004:Studio",
        name="Studio",
        host="mac.local.",
        port=5004,
    )

    config = parse_config(
        {
            "adapters": {
                "rtp_midi": {
                    "enabled": True,
                    "role": "join",
                    "join_target": "mac.local.:5004:Studio",
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

    assert payload["rtp_midi_available"] is True
    assert payload["discovered_rtp_sessions"][0]["name"] == "Studio"
    assert payload["instances"][0]["role"] == "join"
    assert payload["instances"][0]["join_target"] == "mac.local.:5004:Studio"


def test_normalized_rtp_midi_options_rejects_join_without_target() -> None:
    config = parse_config({"adapters": {"rtp_midi": {"enabled": True}}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        rtp_midi_manager=RtpMidiManager(),
    )

    with pytest.raises(ValueError, match="join_target must be selected"):
        interface._normalized_rtp_midi_options(
            {"role": "join", "port": 5004},
            {},
            enabled=True,
        )
