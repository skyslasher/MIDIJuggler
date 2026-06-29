import asyncio

from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind, float_value
from midijuggler.learn import LearnController
from midijuggler.modules.modifier.factor import FactorTransform, apply_factor
from midijuggler.modules.modifier.graph import ModifierGraph

from conftest import gpio_device, midi_device


def test_apply_factor_multiplies_value() -> None:
    transform = FactorTransform(factor=1.5)
    assert apply_factor(400.0, transform) == 600.0


def test_parse_factor_connection() -> None:
    config = parse_config(
        {
            "devices": [gpio_device(), midi_device("midi", adapter="midi")],
            "connections": [
                {
                    "id": "scale-source",
                    "source": "gpio.pin17",
                    "target": "midi.cc_0_64",
                    "modifier": "factor",
                    "factor": 1.5,
                }
            ],
        }
    )
    connection = config.connections[0]
    assert connection.modifier == ModifierKind.FACTOR
    assert connection.factor == 1.5


def test_build_connection_supports_factor_modifier() -> None:
    controller = LearnController()
    connection = controller.build_connection(
        source_datapoint="clock.quarter_ms",
        target_datapoint="fx.delay_time",
        modifier=ModifierKind.FACTOR,
        factor=1.5,
    )
    assert connection.modifier == ModifierKind.FACTOR
    assert connection.factor == 1.5


def test_modifier_graph_applies_factor() -> None:
    store = DataPointStore()
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="scale-delay",
                source="clock.quarter_ms",
                target="fx.delay_time",
                modifier=ModifierKind.FACTOR,
                factor=1.5,
            )
        ],
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None:
            received.append(value.float_value)

    store.subscribe("fx.delay_time", handler)

    async def scenario() -> None:
        await graph.start()
        await store.write(float_value("clock.quarter_ms", 400.0))

    asyncio.run(scenario())
    assert received == [600.0]
