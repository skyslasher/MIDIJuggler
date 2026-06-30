import asyncio

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    ConnectionSpec,
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ModifierKind,
    ValueType,
    float_value,
    midi_message_value,
    trigger_value,
)
from midijuggler.eventbus import EventBus
from midijuggler.events import MidiMessageEvent
from midijuggler.master_clock import MIDI_START, MIDI_TIMING_CLOCK, MasterClock
from midijuggler.modules.build import build_module_registry
from midijuggler.modules.generator.master_clock import MasterClockGenerator
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.device.registry import DeviceRegistry
from midijuggler.web.server import WebInterface

from conftest import midi_device


def test_modifier_graph_passthrough_relays_repeated_midi_clock_ticks() -> None:
    store = DataPointStore()
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="clock-to-midi",
                source="clock.midi_tick",
                target="midi.midi_out",
                modifier=ModifierKind.PASSTHROUGH,
            )
        ],
    )
    received: list[int] = []

    async def handler(value) -> None:
        if value.midi_status is not None:
            received.append(value.midi_status)

    store.subscribe("midi.midi_out", handler)

    async def scenario() -> None:
        await graph.start()
        for _ in range(3):
            await store.write(
                midi_message_value("clock.midi_tick", MIDI_TIMING_CLOCK),
            )

    asyncio.run(scenario())
    assert received == [MIDI_TIMING_CLOCK, MIDI_TIMING_CLOCK, MIDI_TIMING_CLOCK]


def test_modifier_graph_passthrough_relays_midi_messages() -> None:
    store = DataPointStore()
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="clock-to-midi",
                source="clock.midi_tick",
                target="midi.midi_out",
                modifier=ModifierKind.PASSTHROUGH,
            )
        ],
    )
    received: list[int] = []

    async def handler(value) -> None:
        if value.midi_status is not None:
            received.append(value.midi_status)

    store.subscribe("midi.midi_out", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(
            midi_message_value("clock.midi_tick", MIDI_TIMING_CLOCK),
        )

    asyncio.run(scenario())
    assert received == [MIDI_TIMING_CLOCK]


def test_midi_io_module_sends_midi_out_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "adapters": {"midi": {"enabled": True, "output_port": "MIDI Out"}},
            "devices": [midi_device("midi", adapter="midi")],
        }
    )
    bus = EventBus()
    store = DataPointStore()
    adapter = MidiAdapter("midi", config.adapters["midi"], bus, app_config=config)
    adapter._output_address = "20:0"
    sent: list[MidiMessageEvent] = []

    async def capture(event: MidiMessageEvent) -> None:
        sent.append(event)

    monkeypatch.setattr(adapter, "send_midi_message", capture)

    async def scenario() -> None:
        registry = DeviceRegistry.from_config(config)
        _, io_modules = build_module_registry(
            config,
            store,
            bus,
            [adapter],
            MasterClock(config.master_clock, bus),
            WebInterface(
                config,
                bus,
                ClockBpmTracker(),
                MasterClock(config.master_clock, bus),
                datapoint_store=store,
                device_registry=registry,
            ),
            registry,
        )
        await io_modules["midi"].start()
        await store.write(midi_message_value("midi.midi_out", MIDI_START))

    asyncio.run(scenario())
    assert len(sent) == 1
    assert sent[0].status == MIDI_START


def test_master_clock_datapoint_routing_reaches_midi_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "master_clock": {
                "enabled": True,
                "output_targets": ["midi"],
                "send_transport": True,
            },
            "adapters": {"midi": {"enabled": True, "output_port": "MIDI Out"}},
            "devices": [midi_device("midi", adapter="midi")],
        }
    )
    bus = EventBus()
    store = DataPointStore()
    adapter = MidiAdapter("midi", config.adapters["midi"], bus, app_config=config)
    adapter._output_address = "20:0"
    sent: list[MidiMessageEvent] = []

    async def capture(event: MidiMessageEvent) -> None:
        sent.append(event)

    monkeypatch.setattr(adapter, "send_midi_message", capture)
    master_clock = MasterClock(config.master_clock, bus)

    async def scenario() -> None:
        device_registry = DeviceRegistry.from_config(config)
        registry, _io_modules = build_module_registry(
            config,
            store,
            bus,
            [adapter],
            master_clock,
            WebInterface(
                config,
                bus,
                ClockBpmTracker(),
                master_clock,
                datapoint_store=store,
                device_registry=device_registry,
            ),
            device_registry,
        )
        clock_gen = next(
            module
            for module in registry.modules()
            if isinstance(module, MasterClockGenerator)
        )
        master_clock.bind_datapoint_sink(clock_gen)
        await registry.start_all()
        await master_clock.emit_tick()
        await master_clock.start_transport(reset_position=True)

    asyncio.run(scenario())

    assert [event.status for event in sent] == [MIDI_TIMING_CLOCK, MIDI_START]


def test_passthrough_hid_key_starts_master_clock() -> None:
    config = parse_config({"master_clock": {"enabled": True}})
    bus = EventBus()
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, bus)
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    store.register(
        DataPointSpec(
            id=DataPointId("enc", "key_a"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
            protocol="hid",
        )
    )
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="enc-start",
                source="enc.key_a",
                target="clock.start",
                modifier=ModifierKind.PASSTHROUGH,
            )
        ],
    )

    async def scenario() -> None:
        await clock_gen.start()
        await graph.start()
        await store.write(float_value("enc.key_a", 1.0))

    asyncio.run(scenario())

    assert master_clock.running is True


def test_master_clock_datapoint_directions_match_connection_roles() -> None:
    store = DataPointStore()
    clock = MasterClock(parse_config({}).master_clock, EventBus())
    specs = {str(spec.id): spec for spec in MasterClockGenerator(clock, store).datapoints()}

    for point in ("bpm", "running", "midi_tick", "quarter_ms", "eighth_ms", "beat"):
        assert specs[f"clock.{point}"].direction.value == "input"

    for point in ("bpm_set", "bpm_up", "bpm_down", "bpm_huge_up", "bpm_huge_down", "start", "stop", "start_stop", "tap_tempo"):
        assert specs[f"clock.{point}"].direction.value == "output"


def test_start_stop_datapoint_toggles_transport() -> None:
    config = parse_config({"master_clock": {"enabled": True}})
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())

    async def scenario() -> None:
        await clock_gen.start()
        await store.write(trigger_value("clock.start_stop", active=False))
        await store.write(trigger_value("clock.start_stop", active=True))
        assert master_clock.running is True
        await store.write(trigger_value("clock.start_stop", active=False))
        await store.write(trigger_value("clock.start_stop", active=True))
        assert master_clock.running is False

    asyncio.run(scenario())


def test_tap_tempo_datapoint_updates_bpm_on_rising_edge() -> None:
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
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    tap = DataPointId("clock", "tap_tempo")

    async def tap_edge(timestamp: float) -> None:
        await store.write(
            DataPointValue(
                point_id=tap,
                value_type=ValueType.TRIGGER,
                bool_value=False,
                timestamp=timestamp,
            )
        )
        await store.write(
            DataPointValue(
                point_id=tap,
                value_type=ValueType.TRIGGER,
                bool_value=True,
                timestamp=timestamp,
            )
        )

    async def scenario() -> None:
        await clock_gen.start()
        await tap_edge(10.0)
        await tap_edge(10.497)
        await tap_edge(10.994)
        assert master_clock.bpm == pytest.approx(100.0)
        await tap_edge(11.491)
        assert master_clock.bpm == pytest.approx(120.5)

    asyncio.run(scenario())


def test_tap_tempo_datapoint_respects_configured_min_taps() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 100.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "tap_tempo_min_taps": 3,
            }
        }
    )
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    tap = DataPointId("clock", "tap_tempo")

    async def tap_edge(timestamp: float) -> None:
        await store.write(
            DataPointValue(
                point_id=tap,
                value_type=ValueType.TRIGGER,
                bool_value=False,
                timestamp=timestamp,
            )
        )
        await store.write(
            DataPointValue(
                point_id=tap,
                value_type=ValueType.TRIGGER,
                bool_value=True,
                timestamp=timestamp,
            )
        )

    async def scenario() -> None:
        await clock_gen.start()
        await tap_edge(10.0)
        await tap_edge(10.497)
        assert master_clock.bpm == pytest.approx(100.0)
        await tap_edge(10.994)
        assert master_clock.bpm == pytest.approx(120.5)

    asyncio.run(scenario())


def test_repeated_passthrough_bpm_up_steps_tempo() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 120.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
            }
        }
    )
    store = DataPointStore()
    store.register(
        DataPointSpec(
            id=DataPointId("enc", "key_f"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
            protocol="hid",
        )
    )
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="enc-bpm-up",
                source="enc.key_f",
                target="clock.bpm_up",
                modifier=ModifierKind.PASSTHROUGH,
            )
        ],
    )

    async def scenario() -> None:
        await clock_gen.start()
        await graph.start()
        await store.write(float_value("enc.key_f", 0.6))
        await store.write(float_value("enc.key_f", 0.8))
        await store.write(float_value("enc.key_f", 1.0))

    asyncio.run(scenario())

    assert master_clock.bpm == pytest.approx(121.5)


def test_bpm_up_down_use_configured_step_and_quantize() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 120.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "bpm_step": 1.0,
                "bpm_quantize": 1.0,
            }
        }
    )
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())

    async def tap_edge(point: str) -> None:
        await store.write(trigger_value(point, active=False))
        await store.write(trigger_value(point, active=True))

    async def scenario() -> None:
        await clock_gen.start()
        await tap_edge("clock.bpm_up")
        assert master_clock.bpm == pytest.approx(121.0)
        await store.write(float_value("clock.bpm_set", 120.3))
        await tap_edge("clock.bpm_up")
        assert master_clock.bpm == pytest.approx(121.0)
        await tap_edge("clock.bpm_down")
        assert master_clock.bpm == pytest.approx(120.0)

    asyncio.run(scenario())


def test_bpm_huge_up_down_use_configured_huge_step() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 120.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "bpm_huge_step": 10.0,
                "bpm_quantize": 1.0,
            }
        }
    )
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())

    async def tap_edge(point: str) -> None:
        await store.write(trigger_value(point, active=False))
        await store.write(trigger_value(point, active=True))

    async def scenario() -> None:
        await clock_gen.start()
        await tap_edge("clock.bpm_huge_up")
        assert master_clock.bpm == pytest.approx(130.0)
        await tap_edge("clock.bpm_huge_down")
        assert master_clock.bpm == pytest.approx(120.0)

    asyncio.run(scenario())


def test_bpm_up_down_datapoints_step_and_quantize_by_half() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 120.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
            }
        }
    )
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())

    async def tap_edge(point: str) -> None:
        await store.write(trigger_value(point, active=False))
        await store.write(trigger_value(point, active=True))

    async def scenario() -> None:
        await clock_gen.start()
        await tap_edge("clock.bpm_up")
        assert master_clock.bpm == pytest.approx(120.5)
        await store.write(float_value("clock.bpm_set", 120.3))
        await tap_edge("clock.bpm_up")
        assert master_clock.bpm == pytest.approx(121.0)
        await tap_edge("clock.bpm_down")
        assert master_clock.bpm == pytest.approx(120.5)

    asyncio.run(scenario())


def test_bpm_up_while_running_preserves_transport_position() -> None:
    config = parse_config({"master_clock": {"enabled": True, "bpm": 120.0}})
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())

    async def scenario() -> None:
        await clock_gen.start()
        await master_clock.start_transport(reset_position=True)
        for _ in range(7):
            await master_clock.emit_tick()
        await store.write(trigger_value("clock.bpm_up", active=False))
        await store.write(trigger_value("clock.bpm_up", active=True))
        assert master_clock.running is True
        assert master_clock.position_ticks == 7
        assert master_clock.bpm == pytest.approx(120.5)

    asyncio.run(scenario())


def test_tap_tempo_while_running_preserves_transport_position() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 100.0,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
                "tap_tempo_min_taps": 3,
            }
        }
    )
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    tap = DataPointId("clock", "tap_tempo")

    async def tap_edge(timestamp: float) -> None:
        await store.write(
            DataPointValue(
                point_id=tap,
                value_type=ValueType.TRIGGER,
                bool_value=False,
                timestamp=timestamp,
            )
        )
        await store.write(
            DataPointValue(
                point_id=tap,
                value_type=ValueType.TRIGGER,
                bool_value=True,
                timestamp=timestamp,
            )
        )

    async def scenario() -> None:
        await clock_gen.start()
        await master_clock.start_transport(reset_position=True)
        for _ in range(5):
            await master_clock.emit_tick()
        await tap_edge(10.0)
        await tap_edge(10.497)
        await tap_edge(10.994)
        assert master_clock.running is True
        assert master_clock.position_ticks == 5
        assert master_clock.bpm == pytest.approx(120.5)

    asyncio.run(scenario())


def test_clock_beat_pulses_on_click_interval() -> None:
    config = parse_config({"master_clock": {"enabled": True, "click_interval": "quarter"}})
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    received: list[float | None] = []

    async def handler(value: DataPointValue) -> None:
        received.append(value.float_value)

    store.subscribe("clock.beat", handler)

    async def scenario() -> None:
        master_clock.bind_datapoint_sink(clock_gen)
        await clock_gen.start()
        await master_clock.emit_tick()
        assert store.float_value("clock.beat") == 1.0
        await asyncio.sleep(clock_gen._effective_beat_flash_seconds() + 0.02)
        assert store.float_value("clock.beat") == 0.0

    asyncio.run(scenario())

    assert received == [0.0, 1.0, 0.0]


def test_clock_beat_flash_caps_to_click_interval() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 240.0,
                "click_interval": "eighth",
                "beat_flash_ms": 120.0,
            }
        }
    )
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)

    # Eighth note at 240 BPM is 125 ms; flash is capped to 90% of that interval.
    assert clock_gen._effective_beat_flash_seconds() == pytest.approx(0.1125, abs=0.001)


def test_clock_beat_publishes_without_audio_click() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "click_enabled": False,
                "click_interval": "quarter",
            }
        }
    )
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())

    async def scenario() -> None:
        master_clock.bind_datapoint_sink(clock_gen)
        await clock_gen.start()
        await master_clock.emit_tick()
        assert store.float_value("clock.beat") == 1.0

    asyncio.run(scenario())


def test_clock_beat_routes_to_led_via_passthrough() -> None:
    store = DataPointStore()
    master_clock = MasterClock(parse_config({}).master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    store.register(
        DataPointSpec(
            id=DataPointId("xtouch", "layer_a_top_button_1_led"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
            protocol="midi",
        )
    )
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="beat-to-led",
                source="clock.beat",
                target="xtouch.layer_a_top_button_1_led",
                modifier=ModifierKind.PASSTHROUGH,
            )
        ],
    )
    received: list[float | None] = []

    async def handler(value: DataPointValue) -> None:
        received.append(value.float_value)

    store.subscribe("xtouch.layer_a_top_button_1_led", handler)

    async def scenario() -> None:
        master_clock.bind_datapoint_sink(clock_gen)
        await clock_gen.start()
        await graph.start()
        await master_clock.emit_tick()
        await asyncio.sleep(clock_gen._effective_beat_flash_seconds() + 0.02)

    asyncio.run(scenario())

    assert received == [0.0, 1.0, 0.0]
