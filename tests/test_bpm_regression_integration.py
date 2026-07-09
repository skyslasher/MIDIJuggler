"""Integration tests for BPM/beat regression with production-style config."""

import asyncio

import pytest

from conftest import osc_device
from midijuggler.config import parse_config
from midijuggler.clock import MIDI_CLOCK_TICKS_PER_QUARTER
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import float_value
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.events import OscMessageEvent
from midijuggler.modules.interface.bandhelper.module import BandHelperModule
from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
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
        module = next(
            m
            for m in service.module_registry.modules()
            if m.__class__.__name__ == "RotaryDisplayModule"
        )
        service.master_clock.position_ticks = 0
        for _ in range(48):
            await service.master_clock.emit_tick()
        if module._beat_send_task is not None:
            await module._beat_send_task
        await asyncio.sleep(0.05)

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
        if module._beat_send_task is not None:
            await module._beat_send_task
        await asyncio.sleep(0.25)

    asyncio.run(scenario())

    beats = [
        msg
        for batch in capture_sync
        for msg in batch
        if msg[0] == "/midijuggler/rotary/beat" and msg[1][0] == pytest.approx(1.0)
    ]
    assert len(beats) == 2


def test_serial_encoder_bpm_with_bandhelper_disabled(
    monkeypatch: pytest.MonkeyPatch,
    capture_sync: list,
) -> None:
    """Encoder serial BPM must update master clock and GamePi clock.bpm status."""

    config = _production_config()
    config["bandhelper"] = {"enabled": False, "link_enabled": False}
    config["master_clock"] = {
        "enabled": True,
        "bpm": 122.0,
        "auto_start": False,
        "tap_tempo_min_taps": 3,
    }
    service = MIDIJugglerService(parse_config(config))
    _patch_adapters_noop_start(monkeypatch, service)

    async def scenario() -> RotaryDisplayModule:
        await _start_service(service)
        assert not any(
            isinstance(module, BandHelperModule)
            for module in service.module_registry.modules()
        )
        module = next(
            m
            for m in service.module_registry.modules()
            if isinstance(m, RotaryDisplayModule)
        )
        module._serial_connected = True
        await module._handle_serial_line("bpm 140.0\n")
        await service.master_clock.flush_bpm_notifications()
        return module

    asyncio.run(scenario())

    sync = [
        msg
        for batch in capture_sync
        for msg in batch
        if msg[0] == "/midijuggler/rotary/sync"
    ]
    assert service.master_clock.bpm == pytest.approx(140.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(140.0)
    assert service.datapoint_store.float_value("clock.bpm_set") == pytest.approx(140.0)
    assert sync
    assert sync[-1][1][0] == pytest.approx(140.0)


def test_high_bpm_slow_serial_send_delivers_catch_up_beats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []
    clock = {"now": 0.0}

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/ttyACM0",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module.running = True
    module._serial_connected = True
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.time.monotonic",
        lambda: clock["now"],
    )

    async def fake_sleep(duration: float) -> None:
        clock["now"] += duration

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.asyncio.sleep",
        fake_sleep,
    )

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

        def flush(self) -> None:
            return None

    module._serial_port = FakeSerial()

    original_send_serial = module._send_serial

    async def slow_send_serial(payload: str) -> None:
        clock["now"] += 0.04
        await original_send_serial(payload)

    module._send_serial = slow_send_serial

    async def scenario() -> None:
        interval = 60.0 / 170.0
        for _ in range(9):
            module._schedule_beat_send(1.0)
            if module._beat_send_task is not None:
                await module._beat_send_task
            clock["now"] += interval

    asyncio.run(scenario())

    beat_lines = [line for line in serial_payloads if line.startswith("beat ")]
    assert len(beat_lines) == 9


def test_beat_send_serializes_concurrent_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "osc",
                "feedback_host": "192.168.1.70",
                "feedback_port": 9001,
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    order: list[str] = []

    async def tracked_send_osc(self, address: str, arguments: list[object]) -> None:
        order.append("start")
        await asyncio.sleep(0.02)
        order.append("end")

    monkeypatch.setattr(RotaryDisplayModule, "_send_osc", tracked_send_osc)

    async def scenario() -> None:
        module.running = True
        module._schedule_beat_send(1.0)
        while not module._beat_send_in_flight:
            await asyncio.sleep(0)
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert order == ["start", "end", "start", "end"]
