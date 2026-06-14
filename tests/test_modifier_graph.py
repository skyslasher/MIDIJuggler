import asyncio

import pytest

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    ConnectionSpec,
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    ValueType,
    float_value,
)
from midijuggler.modules.modifier.graph import ModifierGraph


def _register_relative_turn(
    store: DataPointStore,
    *,
    relative_encoding: str = "offset_binary",
) -> None:
    store.register(
        DataPointSpec(
            id=DataPointId("xtouch_mini", "layer_a_encoder_1_turn"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
            input_mode="relative",
            relative_encoding=relative_encoding,
            protocol="midi",
        )
    )


def test_modifier_graph_maps_source_to_target() -> None:
    store = DataPointStore()
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="footswitch-to-fader",
                source="gpio.pin17",
                target="midi.main.cc_0_64",
                input_min=0.0,
                input_max=1.0,
                output_min=0.0,
                output_max=127.0,
            )
        ],
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None:
            received.append(value.float_value)

    store.subscribe("midi.main.cc_0_64", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(float_value("gpio.pin17", 1.0))

    asyncio.run(scenario())
    assert received == [127.0]


def test_modifier_graph_subscribes_sources_added_at_runtime() -> None:
    store = DataPointStore()
    graph = ModifierGraph(store, [])
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None:
            received.append(value.float_value)

    store.subscribe("xtouch_mini.layer_a_encoder_1_value", handler)

    async def scenario() -> None:
        await graph.start()
        graph.replace_connections(
            [
                ConnectionSpec(
                    id="fader-to-ring",
                    source="x32./ch/01/mix/fader",
                    target="xtouch_mini.layer_a_encoder_1_value",
                    input_min=0.0,
                    input_max=1.0,
                    output_min=0.0,
                    output_max=127.0,
                )
            ]
        )
        await store.write(
            float_value("x32./ch/01/mix/fader", 0.5, emit_outputs=False)
        )

    asyncio.run(scenario())
    assert received == [63.5]


def test_modifier_graph_applies_relative_encoder_delta() -> None:
    store = DataPointStore()
    _register_relative_turn(store)
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="encoder-to-fader",
                source="xtouch_mini.layer_a_encoder_1_turn",
                target="x32./ch/01/mix/fader",
                input_min=1.0,
                input_max=127.0,
                output_min=0.0,
                output_max=1.0,
            )
        ],
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None:
            received.append(value.float_value)

    store.subscribe("x32./ch/01/mix/fader", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 65.0))
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 66.0))

    asyncio.run(scenario())
    assert received[0] == pytest.approx(0.5 + 1.0 / 63.0)
    assert received[1] == pytest.approx(0.5 + 3.0 / 63.0)


def test_modifier_graph_applies_mcu_encoder_delta() -> None:
    store = DataPointStore()
    _register_relative_turn(store, relative_encoding="mcu")
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="encoder-to-fader",
                source="xtouch_mini.layer_a_encoder_1_turn",
                target="x32./ch/01/mix/fader",
                input_min=1.0,
                input_max=127.0,
                output_min=0.0,
                output_max=1.0,
            )
        ],
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None and value.emit_outputs:
            received.append(value.float_value)

    store.subscribe("x32./ch/01/mix/fader", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 1.0))
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 65.0))

    asyncio.run(scenario())
    assert received[0] == pytest.approx(0.5 + 1.0 / 63.0)
    assert received[1] == pytest.approx(0.5)


def test_modifier_graph_applies_absolute_encoder_delta() -> None:
    store = DataPointStore()
    _register_relative_turn(store, relative_encoding="absolute_delta")
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="encoder-to-fader",
                source="xtouch_mini.layer_a_encoder_1_turn",
                target="x32./ch/01/mix/fader",
                input_min=1.0,
                input_max=127.0,
                output_min=0.0,
                output_max=1.0,
            )
        ],
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None and value.emit_outputs:
            received.append(value.float_value)

    store.subscribe("x32./ch/01/mix/fader", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 64.0))
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 65.0))
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 64.0))

    asyncio.run(scenario())
    assert len(received) == 2
    assert received[0] == pytest.approx(0.5 + 1.0 / 63.0)
    assert received[1] == pytest.approx(0.5)


def test_modifier_graph_relative_accumulator_ignores_echoed_target() -> None:
    store = DataPointStore()
    _register_relative_turn(store, relative_encoding="absolute_delta")
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="encoder-to-fader",
                source="xtouch_mini.layer_a_encoder_1_turn",
                target="x32./ch/01/mix/fader",
                input_min=1.0,
                input_max=127.0,
                output_min=0.0,
                output_max=1.0,
            )
        ],
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None and value.emit_outputs:
            received.append(value.float_value)

    store.subscribe("x32./ch/01/mix/fader", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 64.0))
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 65.0))
        await store.write(
            float_value("x32./ch/01/mix/fader", 0.1, emit_outputs=False)
        )
        await store.write(float_value("xtouch_mini.layer_a_encoder_1_turn", 66.0))

    asyncio.run(scenario())
    assert received[0] == pytest.approx(0.5 + 1.0 / 63.0)
    assert received[1] == pytest.approx(0.5 + 2.0 / 63.0)


def test_modifier_graph_suppresses_encoder_feedback_during_turn() -> None:
    store = DataPointStore()
    _register_relative_turn(store)
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="fader-to-ring",
                source="x32./ch/01/mix/fader",
                target="xtouch_mini.layer_a_encoder_1_value",
                input_min=0.0,
                input_max=1.0,
                output_min=0.0,
                output_max=127.0,
            )
        ],
        feedback_suppress_ms=500,
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None:
            received.append(value.float_value)

    store.subscribe("xtouch_mini.layer_a_encoder_1_value", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(
            float_value("xtouch_mini.layer_a_encoder_1_turn", 65.0, emit_outputs=False)
        )
        await store.write(
            float_value("x32./ch/01/mix/fader", 0.5, emit_outputs=False)
        )

    asyncio.run(scenario())
    assert received == []
