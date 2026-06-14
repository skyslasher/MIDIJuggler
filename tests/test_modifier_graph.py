import asyncio

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import ConnectionSpec, float_value
from midijuggler.modules.modifier.graph import ModifierGraph


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
