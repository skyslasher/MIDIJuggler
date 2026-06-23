"""Tests for compare-before-send in the modifier graph."""

import asyncio

import pytest

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    ConnectionSpec,
    DataPointId,
    DataPointSpec,
    ModifierKind,
    ValueType,
    float_value,
)
from midijuggler.modules.modifier.graph import ModifierGraph


def test_modifier_graph_skips_unchanged_target_value() -> None:
    async def scenario() -> tuple[float | None, float | None]:
        store = DataPointStore()
        store.register(
            DataPointSpec(
                id=DataPointId("wing", "/ch/1/fdr"),
                value_type=ValueType.FLOAT,
                direction="bidirectional",
                value_min=-144.0,
                value_max=10.0,
            )
        )
        store.register(
            DataPointSpec(
                id=DataPointId("xtouch", "layer_a_fader_1"),
                value_type=ValueType.FLOAT,
                direction="output",
                value_min=0.0,
                value_max=127.0,
            )
        )
        await store.write(float_value(DataPointId("xtouch", "layer_a_fader_1"), 64.0))

        graph = ModifierGraph(
            store,
            [
                ConnectionSpec(
                    id="feedback",
                    source="wing./ch/1/fdr",
                    target="xtouch.layer_a_fader_1",
                    modifier=ModifierKind.RANGE_MAP,
                    input_min=-144.0,
                    input_max=10.0,
                    output_min=0.0,
                    output_max=127.0,
                )
            ],
            feedback_suppress_ms=0,
        )
        await graph.start()
        await store.write(float_value(DataPointId("wing", "/ch/1/fdr"), -10.0))
        first = store.float_value("xtouch.layer_a_fader_1")
        await store.write(float_value(DataPointId("wing", "/ch/1/fdr"), -10.0))
        second = store.float_value("xtouch.layer_a_fader_1")
        await graph.stop()
        return first, second

    first, second = asyncio.run(scenario())
    assert first == pytest.approx(110.5, abs=0.5)
    assert second == first
