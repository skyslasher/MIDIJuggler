"""OSC I/O module."""

from __future__ import annotations

import logging

from midijuggler.adapters.osc import OscAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ValueType,
    float_value,
)
from midijuggler.events import MappedEvent
from midijuggler.mapping import MappingRule
from midijuggler.modules.base import IOModule
from midijuggler.osc_library import get_osc_library

LOGGER = logging.getLogger(__name__)


class OscIOModule(IOModule):
    """Expose OSC addresses and library parameters as data points."""

    def __init__(
        self,
        adapter: OscAdapter,
        store: DataPointStore,
        config: AppConfig,
    ) -> None:
        super().__init__(adapter.name, store)
        self.adapter = adapter
        self.config = config
        self._output_points: set[str] = set()

    def datapoints(self) -> list[DataPointSpec]:
        specs: list[DataPointSpec] = []
        library_id = str(self.adapter.config.options.get("osc_library", "")).strip()
        if library_id:
            try:
                library = get_osc_library(library_id)
            except KeyError:
                library = None
            if library is not None:
                for parameter in library.parameters:
                    if parameter.direction == "source":
                        direction = DataPointDirection.INPUT
                    else:
                        # Desk OSC targets are writable and also report state on the same path.
                        direction = DataPointDirection.BIDIRECTIONAL
                    point = parameter.address if parameter.address.startswith("/") else parameter.id
                    specs.append(
                        DataPointSpec(
                            id=DataPointId(self.name, point),
                            value_type=ValueType.FLOAT,
                            direction=direction,
                            label=parameter.label,
                            value_min=float(parameter.value_min),
                            value_max=float(parameter.value_max),
                            protocol="osc",
                        )
                    )
                    if direction in {
                        DataPointDirection.OUTPUT,
                        DataPointDirection.BIDIRECTIONAL,
                    }:
                        self._output_points.add(point)
        return specs

    async def start(self) -> None:
        await super().start()
        for point in self._output_points:
            self.store.subscribe(DataPointId(self.name, point), self._on_output_value)

    async def stop(self) -> None:
        await super().stop()

    async def _on_output_value(self, value: DataPointValue) -> None:
        if not value.emit_outputs or value.float_value is None:
            return
        target = f"{self.name}:{value.point_id.point}"
        await self.adapter.send(
            MappedEvent(
                source="datapoint",
                target=target,
                value=value.float_value,
            )
        )
