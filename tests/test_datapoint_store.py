import asyncio

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    ValueType,
    float_value,
)


def test_register_and_write_float_value() -> None:
    store = DataPointStore()
    store.register(
        DataPointSpec(
            id=DataPointId("gpio", "pin17"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
        )
    )
    received: list[float] = []

    async def handler(value):
        if value.float_value is not None:
            received.append(value.float_value)

    store.subscribe(DataPointId("gpio", "pin17"), handler)

    async def scenario() -> None:
        await store.write(float_value(DataPointId("gpio", "pin17"), 1.0))

    asyncio.run(scenario())
    assert received == [1.0]
    assert store.snapshot()["gpio.pin17"]["float_value"] == 1.0


def test_subscribe_all_receives_updates() -> None:
    store = DataPointStore()
    seen: list[str] = []

    async def handler(value):
        seen.append(str(value.point_id))

    store.subscribe_all(handler)

    async def scenario() -> None:
        await store.write(float_value("osc.desk./test", 0.5))

    asyncio.run(scenario())
    assert seen == ["osc.desk./test"]


def test_registry_snapshot_includes_specs() -> None:
    store = DataPointStore()
    store.register(
        DataPointSpec(
            id=DataPointId("clock", "bpm"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
            label="BPM",
        )
    )
    payload = store.registry_snapshot()
    assert payload[0]["id"] == "clock.bpm"
    assert payload[0]["label"] == "BPM"
