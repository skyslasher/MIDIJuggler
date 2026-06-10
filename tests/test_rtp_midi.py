import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from midijuggler.config import AdapterConfig, parse_config
from midijuggler.clock import ClockBpmTracker
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.rtp_midi.avahi import (
    _AVAHI_BROWSE_ARGS,
    avahi_tool_paths,
    parse_avahi_browse_line,
)
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


def test_avahi_browse_args_do_not_use_all_flag_with_service_type() -> None:
    assert "-a" not in _AVAHI_BROWSE_ARGS
    assert _AVAHI_BROWSE_ARGS == ("-r", "-p", "-t")


def test_avahi_tool_paths_fall_back_to_usr_bin(tmp_path, monkeypatch) -> None:
    publish = tmp_path / "avahi-publish-service"
    browse = tmp_path / "avahi-browse"
    publish.write_text("#!/bin/sh\n", encoding="utf-8")
    browse.write_text("#!/bin/sh\n", encoding="utf-8")
    publish.chmod(0o755)
    browse.chmod(0o755)

    monkeypatch.setattr(
        "midijuggler.rtp_midi.avahi._PUBLISH_CANDIDATES",
        ("missing-publish", str(publish)),
    )
    monkeypatch.setattr(
        "midijuggler.rtp_midi.avahi._BROWSE_CANDIDATES",
        ("missing-browse", str(browse)),
    )
    monkeypatch.setattr("midijuggler.rtp_midi.avahi.shutil.which", lambda _: None)

    assert avahi_tool_paths() == (str(publish), str(browse))


def test_parse_avahi_browse_line_extracts_session() -> None:
    line = "=;eth0;IPv4;MIDIJuggler;_apple-midi._udp;local;MIDIJuggler.local;192.168.1.10;5004;\"\""
    session = parse_avahi_browse_line(line)

    assert session is not None
    assert session.name == "MIDIJuggler"
    assert session.host == "MIDIJuggler.local."
    assert session.port == 5004
    assert session.addresses == ("192.168.1.10",)


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


def test_rtp_midi_manager_uses_avahi_backend_when_tools_exist(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.rtp_midi.manager.avahi_tools_available", lambda: True)
    monkeypatch.setattr("midijuggler.rtp_midi.manager.zeroconf_available", lambda: True)

    discovery = MagicMock()
    discovery.start = AsyncMock()
    discovery.stop = AsyncMock()
    discovery.sessions = MagicMock(return_value=[])
    announcer = MagicMock()
    announcer.start = AsyncMock()
    announcer.stop = AsyncMock()

    monkeypatch.setattr(
        "midijuggler.rtp_midi.manager.avahi_tool_paths",
        lambda: ("/usr/bin/avahi-publish-service", "/usr/bin/avahi-browse"),
    )
    monkeypatch.setattr(
        "midijuggler.rtp_midi.manager.AvahiRtpMidiDiscovery",
        lambda browse_path: discovery,
    )
    monkeypatch.setattr(
        "midijuggler.rtp_midi.manager.AvahiRtpMidiAnnouncer",
        lambda session_name, port, publish_path: announcer,
    )

    async def exercise() -> None:
        manager = RtpMidiManager()
        await manager.start()
        assert manager.backend == "avahi"
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


def test_rtp_midi_manager_hosts_enabled_instance_with_zeroconf(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.rtp_midi.manager.avahi_tools_available", lambda: False)
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
        assert manager.backend == "zeroconf"
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


def test_joinable_sessions_exclude_local_host() -> None:
    manager = RtpMidiManager()
    local_host = local_mdns_server_name()
    local_id = rtp_session_id("MIDIJuggler", local_host, 5004)
    remote_id = rtp_session_id("MacSession", "MacBook.local.", 5004)
    manager._discovery = RtpMidiDiscovery()
    manager._discovery._sessions = {
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
    manager._instances["rtp_midi"] = AdapterConfig(
        enabled=True,
        kind="rtp_midi",
        options={"role": "host", "session_name": "MIDIJuggler", "port": 5004},
    )
    manager._announcers["rtp_midi"] = object()

    joinable = manager.joinable_sessions()

    assert [session["id"] for session in joinable] == [remote_id]


def test_hosted_session_ids_tracks_active_host_instances() -> None:
    manager = RtpMidiManager()
    manager._instances["rtp_midi"] = AdapterConfig(
        enabled=True,
        kind="rtp_midi",
        options={"role": "host", "session_name": "MIDIJuggler", "port": 5004},
    )
    manager._announcers["rtp_midi"] = MagicMock()

    hosted_ids = manager.hosted_session_ids()

    assert len(hosted_ids) == 1
    assert list(hosted_ids)[0].endswith(":MIDIJuggler")


def test_midi_payload_includes_rtp_discovery_fields(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.web.server.list_midi_ports", lambda: [])
    manager = RtpMidiManager()
    manager._discovery = RtpMidiDiscovery()
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
