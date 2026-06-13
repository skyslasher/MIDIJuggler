"""GPIO I/O module."""

from __future__ import annotations

from midijuggler.adapters.gpio import GpioAdapter
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ValueType,
)
from midijuggler.modules.base import IOModule


class GpioIOModule(IOModule):
    """Expose configured GPIO pins as input data points."""

    def __init__(self, adapter: GpioAdapter, store: DataPointStore) -> None:
        super().__init__(adapter.name, store)
        self.adapter = adapter

    def datapoints(self) -> list[DataPointSpec]:
        specs: list[DataPointSpec] = []
        for gpio_input in self.adapter.inputs:
            point_id = DataPointId(self.name, gpio_input.control)
            specs.append(
                DataPointSpec(
                    id=point_id,
                    value_type=ValueType.FLOAT,
                    direction=DataPointDirection.INPUT,
                    label=f"GPIO pin {gpio_input.pin}",
                    value_min=0.0,
                    value_max=1.0,
                    protocol="gpio",
                )
            )
        return specs

    async def start(self) -> None:
        await super().start()

    async def stop(self) -> None:
        await super().stop()
