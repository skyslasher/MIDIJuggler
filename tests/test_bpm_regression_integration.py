"""Integration tests for BPM/beat regression with production-style config."""

import asyncio
import time

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
        service.master_clock.running = True
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
        service.master_clock.running = True
        module._on_transport_beat_pulse()
        await asyncio.sleep(0.05)
        module._on_transport_beat_pulse()
        await asyncio.sleep(0.05)

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


def test_high_bpm_slow_serial_send_delivers_live_beats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []

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
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

        def flush(self) -> None:
            return None

    module._serial_port = FakeSerial()

    original_send_serial = module._send_serial

    async def slow_send_serial(payload: str) -> None:
        await asyncio.sleep(0.04)
        await original_send_serial(payload)

    module._send_serial = slow_send_serial

    async def scenario() -> None:
        for _ in range(9):
            module._schedule_beat_send(1.0)
            if module._beat_send_task is not None:
                await module._beat_send_task

    asyncio.run(scenario())

    beat_lines = [line for line in serial_payloads if line.startswith("beat ")]
    assert len(beat_lines) == 9


def test_clock_beat_publishes_nine_of_nine_at_170_bpm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _production_config()
    config["master_clock"]["bpm"] = 170.0
    service = MIDIJugglerService(parse_config(config))
    _patch_adapters_noop_start(monkeypatch, service)
    beat_ones: list[float] = []

    async def capture_beat(value):
        if value.float_value is not None and value.float_value > 0.5:
            beat_ones.append(value.float_value)

    async def scenario() -> None:
        service.datapoint_store.subscribe("clock.beat", capture_beat)
        await _start_service(service)
        service.master_clock.running = True
        beat_ticks = MIDI_CLOCK_TICKS_PER_QUARTER * 9
        for _ in range(beat_ticks):
            await service.master_clock.emit_tick()
        module = next(
            m
            for m in service.module_registry.modules()
            if isinstance(m, RotaryDisplayModule)
        )
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert len(beat_ones) == 9


def test_gamepi_style_subscriber_gets_nine_of_nine_at_170_bpm_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClickPlayer:
        def trigger(self) -> None:
            return

        async def play(self) -> None:
            return

        async def close(self) -> None:
            return

    config = _production_config()
    config["master_clock"]["bpm"] = 170.0
    config["master_clock"]["click_enabled"] = False
    service = MIDIJugglerService(parse_config(config))
    _patch_adapters_noop_start(monkeypatch, service)
    flashes: list[float] = []

    async def gamepi_handler(value) -> None:
        if value.float_value is not None and value.float_value > 0.5:
            flashes.append(value.float_value)
        await asyncio.sleep(0.03)

    async def scenario() -> None:
        service.datapoint_store.subscribe("clock.beat", gamepi_handler)
        await _start_service(service)
        service.master_clock.click_player = FakeClickPlayer()
        await service.master_clock.start_transport(reset_position=True)
        await asyncio.sleep(3.2)
        await service.master_clock.stop_transport()

    asyncio.run(scenario())

    assert len(flashes) >= 9


def test_osc_beat_burst_coalesces_and_drain_does_not_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    osc_starts: list[float] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    module.running = True
    module._register_feedback_target("192.168.1.70", 9001)
    master_clock.running = True

    async def slow_send_osc(self, address: str, arguments: list[object]) -> None:
        osc_starts.append(time.monotonic())
        await asyncio.sleep(0.04)

    monkeypatch.setattr(RotaryDisplayModule, "_send_osc", slow_send_osc)

    async def scenario() -> None:
        started = time.monotonic()
        for _ in range(9):
            module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task
        elapsed = time.monotonic() - started
        assert elapsed < 0.2

    asyncio.run(scenario())

    assert len(osc_starts) == 1


def test_beat_send_coalesces_concurrent_burst(
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
        master_clock.running = True
        module._register_feedback_target("192.168.1.70", 9001)
        module._schedule_beat_send(1.0)
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task
        await asyncio.sleep(0.05)

    asyncio.run(scenario())

    assert order.count("start") == 1
    assert order.count("end") == 1
