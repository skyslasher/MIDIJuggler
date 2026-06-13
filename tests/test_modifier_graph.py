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
