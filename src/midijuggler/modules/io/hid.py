"""HID I/O module."""

from __future__ import annotations

from midijuggler.adapters.hid import HidAdapter
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    ValueType,
)
from midijuggler.modules.base import IOModule


class HidIOModule(IOModule):
    """Expose configured HID controls as input data points."""

    def __init__(self, adapter: HidAdapter, store: DataPointStore) -> None:
        super().__init__(adapter.name, store)
        self.adapter = adapter

    def datapoints(self) -> list[DataPointSpec]:
        specs: list[DataPointSpec] = []
        for hid_input in self.adapter.inputs:
            specs.append(
                DataPointSpec(
                    id=DataPointId(self.name, hid_input.control),
                    value_type=ValueType.FLOAT,
                    direction=DataPointDirection.INPUT,
                    label=hid_input.code_name,
                    value_min=hid_input.value_min,
                    value_max=hid_input.value_max,
                    protocol="hid",
                )
            )
        return specs

    async def start(self) -> None:
        await super().start()

    async def stop(self) -> None:
        await super().stop()
