import asyncio

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind, midi_message_value
from midijuggler.eventbus import EventBus
from midijuggler.events import MidiMessageEvent
from midijuggler.master_clock import MIDI_START, MIDI_TIMING_CLOCK, MasterClock
from midijuggler.modules.build import build_module_registry
from midijuggler.modules.generator.master_clock import MasterClockGenerator
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.web.server import WebInterface


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
            ),
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
            ),
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


def test_master_clock_datapoint_directions_match_connection_roles() -> None:
    store = DataPointStore()
    clock = MasterClock(parse_config({}).master_clock, EventBus())
    specs = {str(spec.id): spec for spec in MasterClockGenerator(clock, store).datapoints()}

    for point in ("bpm", "running", "midi_tick", "quarter_ms", "eighth_ms"):
        assert specs[f"clock.{point}"].direction.value == "input"

    for point in ("bpm_set", "bpm_up", "bpm_down", "start", "stop"):
        assert specs[f"clock.{point}"].direction.value == "output"
