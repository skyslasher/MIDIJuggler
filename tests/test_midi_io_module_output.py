import asyncio
from unittest.mock import AsyncMock

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import parse_config
from midijuggler.datapoint.bridge import EventToDataPointBridge
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointId, DataPointValue, ValueType, float_value
from midijuggler.device.registry import DeviceRegistry
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, MidiMessageEvent, OscMessageEvent

from conftest import gpio_device, make_midi_io_module, midi_device


def test_midi_io_module_sends_connection_targets_without_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> MidiMessageEvent | None:
        config = parse_config(
            {
                "adapters": {
                    "gpio": {"enabled": True, "pins": [17]},
                    "xtouch_mini": {
                        "enabled": True,
                        "type": "midi",
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                    },
                },
                "devices": [
                    gpio_device(),
                    midi_device("xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "gpio-to-xtouch-cc",
                        "source": "gpio.pin17",
                        "target": "xtouch_mini.cc_1_64",
                    }
                ],
            }
        )
        bus = EventBus()
        events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: events.append(event))

        store = DataPointStore()
        module, adapter, _registry = make_midi_io_module(config, store, bus=bus)
        monkeypatch.setattr(
            adapter,
            "send_midi_message",
            lambda event: events.append(event),
        )

        await module.start()
        await store.write(float_value("xtouch_mini.cc_1_64", 80.0))
        return next((event for event in events if event.direction == "output"), None)

    output_event = asyncio.run(scenario())

    assert output_event is not None
    assert output_event.status == 0xB0
    assert output_event.data == (64, 80)


def test_midi_io_module_sends_program_change_connection_target_without_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> MidiMessageEvent | None:
        config = parse_config(
            {
                "adapters": {
                    "gpio": {"enabled": True, "pins": [17]},
                    "xtouch_mini": {
                        "enabled": True,
                        "type": "midi",
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                    },
                },
                "devices": [
                    gpio_device(),
                    midi_device("xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "gpio-to-xtouch-program",
                        "source": "gpio.pin17",
                        "target": "xtouch_mini.program_11_1",
                        "input_min": 0.0,
                        "input_max": 1.0,
                        "output_min": 0.0,
                        "output_max": 1.0,
                    }
                ],
            }
        )
        bus = EventBus()
        events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: events.append(event))

        store = DataPointStore()
        module, adapter, _registry = make_midi_io_module(config, store, bus=bus)
        monkeypatch.setattr(
            adapter,
            "send_midi_message",
            lambda event: events.append(event),
        )

        await module.start()
        await store.write(float_value("xtouch_mini.program_11_1", 1.0))
        return next((event for event in events if event.direction == "output"), None)

    output_event = asyncio.run(scenario())

    assert output_event is not None
    assert output_event.status == 0xCA
    assert output_event.data == (1,)


def test_midi_io_module_sends_program_change_library_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> MidiMessageEvent | None:
        config = parse_config(
            {
                "adapters": {
                    "xtouch_mini": {
                        "enabled": True,
                        "type": "midi",
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    }
                },
                "devices": [
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
            }
        )
        bus = EventBus()
        events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: events.append(event))

        store = DataPointStore()
        module, adapter, _registry = make_midi_io_module(config, store, bus=bus)
        monkeypatch.setattr(
            adapter,
            "send_midi_message",
            lambda event: events.append(event),
        )

        await module.start()
        await store.write(float_value("xtouch_mini.select_layer_b", 1.0))
        return next((event for event in events if event.direction == "output"), None)

    output_event = asyncio.run(scenario())

    assert output_event is not None
    assert output_event.status == 0xCA
    assert output_event.data == (1,)


def test_midi_io_module_does_not_echo_input_sourced_datapoint_writes() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "input_port": "X-TOUCH MINI",
                    "output_port": "X-TOUCH MINI",
                    "midi_library": "behringer_xtouch_mini",
                }
            },
            "devices": [
                midi_device("xtouch_mini", library="behringer_xtouch_mini"),
            ],
        }
    )
    store = DataPointStore()
    bus = EventBus()
    module, adapter, _registry = make_midi_io_module(config, store, bus=bus)
    store.register_many(module.datapoints())
    adapter.send_midi_message = AsyncMock()

    async def scenario() -> None:
        await module.start()
        await store.write(
            float_value("xtouch_mini.layer_a_encoder_1_value", 64.0, emit_outputs=False)
        )
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_value", 100.0))

    asyncio.run(scenario())

    adapter.send_midi_message.assert_awaited_once()
    sent = adapter.send_midi_message.await_args.args[0]
    assert sent.direction == "output"
    assert sent.data == (1, 100)


def test_midi_io_module_remembers_feedback_without_emitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from midijuggler.midi.xtouch_feedback import XTouchFeedbackRefresh

    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "input_port": "X-TOUCH MINI",
                    "output_port": "X-TOUCH MINI",
                    "midi_library": "behringer_xtouch_mini",
                    "feedback_refresh_interval": 0.1,
                }
            },
            "devices": [
                midi_device("xtouch_mini", library="behringer_xtouch_mini"),
            ],
        }
    )
    store = DataPointStore()
    bus = EventBus()
    module, adapter, _registry = make_midi_io_module(config, store, bus=bus)
    store.register_many(module.datapoints())
    adapter.send_midi_message = AsyncMock()
    adapter._feedback_refresh = XTouchFeedbackRefresh(adapter, config)
    adapter._feedback_refresh.configure(config.adapters["xtouch_mini"], config)

    async def scenario() -> None:
        await module.start()
        await store.write(
            float_value(
                "xtouch_mini.layer_a_encoder_1_led_ring",
                12.0,
                emit_outputs=False,
            )
        )

    asyncio.run(scenario())

    assert adapter._feedback_refresh._cache["layer_a_encoder_1_led_ring"] == 12.0
    adapter.send_midi_message.assert_not_awaited()


def test_bridge_midi_control_event_does_not_emit_outputs() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                }
            },
            "devices": [
                midi_device("xtouch_mini", library="behringer_xtouch_mini"),
            ],
        }
    )
    store = DataPointStore()
    bus = EventBus()
    registry = DeviceRegistry.from_config(config)
    bridge = EventToDataPointBridge(store, bus, registry)
    captured: list[DataPointValue] = []

    async def capture(value: DataPointValue) -> None:
        captured.append(value)

    store.subscribe(DataPointId("xtouch_mini", "layer_a_fader"), capture)
    bridge.attach()

    async def scenario() -> None:
        await bus.publish(
            ControlEvent(
                source="xtouch_mini",
                control="layer_a_fader",
                value=64.0,
            )
        )

    asyncio.run(scenario())

    assert len(captured) == 1
    assert captured[0].float_value == 64.0
    assert captured[0].emit_outputs is False


def test_bridge_midi_program_change_input_writes_datapoint_without_emitting_outputs() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "input_port": "X-TOUCH MINI",
                    "output_port": "X-TOUCH MINI",
                }
            },
            "devices": [midi_device("xtouch_mini")],
        }
    )
    store = DataPointStore()
    bus = EventBus()
    registry = DeviceRegistry.from_config(config)
    bridge = EventToDataPointBridge(store, bus, registry)
    captured: list[DataPointValue] = []

    async def capture(value: DataPointValue) -> None:
        captured.append(value)

    store.subscribe(DataPointId("xtouch_mini", "program_10_1"), capture)
    bridge.attach()

    async def scenario() -> None:
        await bus.publish(
            MidiMessageEvent(
                source="xtouch_mini",
                status=0xCA,
                data=(1,),
                direction="input",
            )
        )

    asyncio.run(scenario())

    assert len(captured) == 1
    assert captured[0].value_type == ValueType.MIDI_MESSAGE
    assert captured[0].midi_status == 0xCA
    assert captured[0].midi_data == (1,)
    assert captured[0].emit_outputs is False


def test_bridge_skips_osc_control_events() -> None:
    config = parse_config(
        {
            "adapters": {
                "x32": {"enabled": True, "type": "osc", "osc_library": "behringer_x32"}
            },
            "devices": [{"id": "x32", "adapter": "x32", "library": "behringer_x32", "library_kind": "osc"}],
        }
    )
    store = DataPointStore()
    bus = EventBus()
    registry = DeviceRegistry.from_config(config)
    bridge = EventToDataPointBridge(store, bus, registry)
    captured: list[DataPointValue] = []

    async def capture(value: DataPointValue) -> None:
        captured.append(value)

    store.subscribe(DataPointId("x32", "/ch/01/mix/fader"), capture)
    bridge.attach()

    async def scenario() -> None:
        await bus.publish(
            OscMessageEvent(
                source="x32",
                address="/ch/01/mix/fader",
                arguments=(0.5,),
                direction="input",
            )
        )
        await bus.publish(
            ControlEvent(
                source="x32",
                control="/ch/01/mix/fader",
                value=0.5,
            )
        )

    asyncio.run(scenario())

    float_captures = [value for value in captured if value.value_type == ValueType.FLOAT]
    assert len(float_captures) == 1
    assert float_captures[0].float_value == 0.5


def test_bridge_midi_control_event_does_not_echo_output_subscribed_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "input_port": "X-TOUCH MINI",
                    "output_port": "X-TOUCH MINI",
                    "midi_library": "behringer_xtouch_mini",
                }
            },
            "devices": [
                midi_device("xtouch_mini", library="behringer_xtouch_mini"),
            ],
        }
    )
    bus = EventBus()
    events: list[MidiMessageEvent] = []
    bus.subscribe(MidiMessageEvent, lambda event: events.append(event))

    store = DataPointStore()
    module, adapter, registry = make_midi_io_module(config, store, bus=bus)
    monkeypatch.setattr(
        adapter,
        "send_midi_message",
        lambda event: events.append(event),
    )
    store.register_many(module.datapoints())
    bridge = EventToDataPointBridge(store, bus, registry)

    async def scenario() -> list[MidiMessageEvent]:
        await module.start()
        bridge.attach()
        await bus.publish(
            ControlEvent(
                source="xtouch_mini",
                control="layer_a_encoder_1_led_ring",
                value=12.0,
            )
        )
        return [event for event in events if event.direction == "output"]

    output_events = asyncio.run(scenario())

    assert output_events == []
