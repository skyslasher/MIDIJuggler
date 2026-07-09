"""Integration tests for BPM set/sync paths with datapoint routing."""

import asyncio

import pytest

from conftest import osc_device
from midijuggler.config import parse_config
from midijuggler.events import OscMessageEvent
from midijuggler.osc.protocol import decode_messages
from midijuggler.service import MIDIJugglerService


def _patch_adapters_noop_start(monkeypatch: pytest.MonkeyPatch, service: MIDIJugglerService) -> None:
    async def fake_start(adapter) -> None:
        adapter.running = True

    async def fake_stop(adapter) -> None:
        adapter.running = False

    for adapter in service.adapters:
        monkeypatch.setattr(adapter, "start", lambda adapter=adapter: fake_start(adapter))
        monkeypatch.setattr(adapter, "stop", lambda adapter=adapter: fake_stop(adapter))


async def _start_service(service: MIDIJugglerService) -> None:
    await service.rtp_midi_manager.start()
    await service.osc_desk_tracker.start()
    await service.module_registry.start_all()
    await service.web.refresh_all_device_datapoints()
    if service.web.modifier_graph is not None:
        await service.web.modifier_graph.replay_subscribed_sources_from_store()
    service.event_bridge.attach()
    await service.master_clock.start()


def _rotary_config(**runtime: object) -> dict:
    return {
        "runtime": {"datapoint_routing": True, **runtime},
        "master_clock": {"enabled": True, "bpm": 120.0, "tap_tempo_min_taps": 3},
        "adapters": {"osc": {"enabled": True, "type": "osc", "listen_port": 9000}},
        "devices": [osc_device("rotary_encoder", "rotary_display", adapter="osc")],
        "rotary_display": {
            "enabled": True,
            "transport": "osc",
            "feedback_host": "192.168.1.70",
            "feedback_port": 9001,
        },
    }


@pytest.fixture
def capture_sync(monkeypatch: pytest.MonkeyPatch):
    sent: list = []

    def fake_udp(payload: bytes, host: str, port: int, **kwargs: object) -> None:
        sent.append(decode_messages(payload))

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        fake_udp,
    )
    return sent


def test_full_bus_osc_updates_master_clock_and_sync(
    monkeypatch: pytest.MonkeyPatch,
    capture_sync: list,
) -> None:
    service = MIDIJugglerService(parse_config(_rotary_config()))
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> None:
        await _start_service(service)
        await service.bus.publish(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(140.0,),
            )
        )
        await service.master_clock.flush_bpm_notifications()
        await asyncio.sleep(0.05)

    asyncio.run(scenario())

    sync = [msg for batch in capture_sync for msg in batch if msg[0] == "/midijuggler/rotary/sync"]
    assert service.master_clock.bpm == pytest.approx(140.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(140.0)
    assert sync
    assert sync[-1][1][0] == pytest.approx(140.0)


def test_web_master_clock_bpm_change_updates_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MIDIJugglerService(parse_config(_rotary_config()))
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> None:
        await _start_service(service)
        await service.web.apply_master_clock_config(
            {
                "enabled": True,
                "bpm": 135.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "output_targets": [],
            }
        )
        await service.master_clock.flush_bpm_notifications()
        await asyncio.sleep(0.05)

    asyncio.run(scenario())

    assert service.master_clock.bpm == pytest.approx(135.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(135.0)
    assert service.datapoint_store.float_value("clock.bpm_set") == pytest.approx(135.0)


def test_tap_tempo_sync_matches_master_clock(
    monkeypatch: pytest.MonkeyPatch,
    capture_sync: list,
) -> None:
    service = MIDIJugglerService(parse_config(_rotary_config()))
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> None:
        await _start_service(service)
        for timestamp in (10.0, 10.48, 10.96, 11.44):
            await service.web.apply_clock_trigger("tap_tempo", timestamp=timestamp)
        await service.master_clock.flush_bpm_notifications()
        await asyncio.sleep(0.05)

    asyncio.run(scenario())

    expected = service.master_clock.bpm
    sync = [msg for batch in capture_sync for msg in batch if msg[0] == "/midijuggler/rotary/sync"]
    assert expected != pytest.approx(120.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(expected)
    assert sync
    assert sync[-1][1][0] == pytest.approx(expected)


def test_no_device_osc_updates_via_service_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MIDIJugglerService(
        parse_config(
            {
                "runtime": {
                    "datapoint_routing": True,
                    "suppressed_inferred_device_adapters": ["osc"],
                },
                "master_clock": {"enabled": True, "bpm": 120.0},
                "adapters": {"osc": {"enabled": True, "type": "osc", "listen_port": 9000}},
                "devices": [],
                "rotary_display": {"enabled": True, "transport": "osc"},
            }
        )
    )
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> None:
        await _start_service(service)
        await service.bus.publish(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(140.0,),
            )
        )
        await service.master_clock.flush_bpm_notifications()

    asyncio.run(scenario())
    assert service.master_clock.bpm == pytest.approx(140.0)
