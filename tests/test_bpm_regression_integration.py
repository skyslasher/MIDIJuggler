"""Integration tests for BPM/beat regression with production-style config."""

import asyncio

import pytest

from conftest import osc_device
from midijuggler.config import parse_config
from midijuggler.datapoint.types import float_value
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


def _production_config(**runtime: object) -> dict:
    return {
        "runtime": {"datapoint_routing": True, **runtime},
        "master_clock": {
            "enabled": True,
            "bpm": 120.0,
            "auto_start": False,
            "tap_tempo_min_taps": 3,
        },
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


def test_bus_osc_updates_master_clock_and_sync(
    monkeypatch: pytest.MonkeyPatch,
    capture_sync: list,
) -> None:
    service = MIDIJugglerService(parse_config(_production_config()))
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

    sync = [msg for batch in capture_sync for msg in batch if msg[0] == "/midijuggler/rotary/sync"]
    assert service.master_clock.bpm == pytest.approx(140.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(140.0)
    assert sync
    assert sync[-1][1][0] == pytest.approx(140.0)


def test_web_master_clock_bpm_change_with_datapoint_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MIDIJugglerService(parse_config(_production_config()))
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

    asyncio.run(scenario())

    assert service.master_clock.bpm == pytest.approx(135.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(135.0)


def test_tap_tempo_updates_master_clock_and_sync(
    monkeypatch: pytest.MonkeyPatch,
    capture_sync: list,
) -> None:
    service = MIDIJugglerService(parse_config(_production_config()))
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> None:
        await _start_service(service)
        for timestamp in (10.0, 10.48, 10.96, 11.44):
            await service.web.apply_clock_trigger("tap_tempo", timestamp=timestamp)
        await service.master_clock.flush_bpm_notifications()

    asyncio.run(scenario())

    expected = service.master_clock.bpm
    sync = [msg for batch in capture_sync for msg in batch if msg[0] == "/midijuggler/rotary/sync"]
    assert expected != pytest.approx(120.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(expected)
    assert sync
    assert sync[-1][1][0] == pytest.approx(expected)


def test_beat_reaches_rotary_display_with_datapoint_routing(
    monkeypatch: pytest.MonkeyPatch,
    capture_sync: list,
) -> None:
    service = MIDIJugglerService(parse_config(_production_config()))
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> None:
        await _start_service(service)
        await service.master_clock.start_transport(reset_position=True)
        for _ in range(48):
            await service.master_clock.emit_tick()

    asyncio.run(scenario())

    beats = [
        msg
        for batch in capture_sync
        for msg in batch
        if msg[0] == "/midijuggler/rotary/beat" and msg[1][0] == pytest.approx(1.0)
    ]
    assert len(beats) >= 2


def test_beat_rising_edge_survives_repeated_one_values(
    monkeypatch: pytest.MonkeyPatch,
    capture_sync: list,
) -> None:
    service = MIDIJugglerService(parse_config(_production_config()))
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> None:
        await _start_service(service)
        module = next(
            m
            for m in service.module_registry.modules()
            if m.__class__.__name__ == "RotaryDisplayModule"
        )
        module._beat_pulse_active = True
        module._last_beat = 1.0
        await service.datapoint_store.write(float_value("clock.beat", 1.0, force_notify=True))
        await service.datapoint_store.write(float_value("clock.beat", 0.0, force_notify=True))
        await service.datapoint_store.write(float_value("clock.beat", 1.0, force_notify=True))

    asyncio.run(scenario())

    beats = [
        msg
        for batch in capture_sync
        for msg in batch
        if msg[0] == "/midijuggler/rotary/beat" and msg[1][0] == pytest.approx(1.0)
    ]
    assert len(beats) == 1
