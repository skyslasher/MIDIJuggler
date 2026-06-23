"""Wing native I/O module."""

from __future__ import annotations

from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.migrate import effective_connections
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
from midijuggler.modules.base import IOModule
from midijuggler.osc_library import get_osc_library


class WingNativeIOModule(IOModule):
    """Expose Wing library parameters as data points over the native TCP protocol."""

    def __init__(
        self,
        adapter: WingNativeAdapter,
        store: DataPointStore,
        config: AppConfig,
    ) -> None:
        super().__init__(adapter.name, store)
        self.adapter = adapter
        self.config = config
        self._output_points: set[str] = set()

    def datapoints(self) -> list[DataPointSpec]:
        specs: list[DataPointSpec] = []
        library_id = str(self.adapter.config.options.get("wing_library", "behringer_wing")).strip()
        if not library_id:
            return specs
        try:
            library = get_osc_library(library_id)
        except KeyError:
            return specs

        for parameter in library.parameters:
            if parameter.direction == "source":
                direction = DataPointDirection.INPUT
            else:
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
                    protocol="wing_native",
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
        for point_id in self._configured_output_targets():
            if point_id.point in self._output_points:
                continue
            self._output_points.add(point_id.point)
            self.store.subscribe(point_id, self._on_output_value)

    def _configured_output_targets(self) -> list[DataPointId]:
        connections = effective_connections(
            self.config.mappings,
            self.config.connections,
            datapoint_routing=self.config.runtime.datapoint_routing,
            master_clock=self.config.master_clock,
            adapters=self.config.adapters,
        )
        targets: list[DataPointId] = []
        seen: set[str] = set()
        for connection in connections:
            parsed = DataPointId.parse(connection.target)
            if parsed.module != self.name:
                continue
            for point in (parsed.point, self._library_address_for_point(parsed.point)):
                if point is None or point in seen:
                    continue
                seen.add(point)
                targets.append(DataPointId(self.name, point))
        return targets

    def _library_address_for_point(self, point: str) -> str | None:
        if point.startswith("/"):
            return None
        library_id = str(self.adapter.config.options.get("wing_library", "behringer_wing")).strip()
        if not library_id:
            return None
        try:
            library = get_osc_library(library_id)
        except KeyError:
            return None
        for parameter in library.parameters:
            if parameter.id != point:
                continue
            address = parameter.address if parameter.address.startswith("/") else parameter.id
            if address != point:
                return address
        return None

    async def stop(self) -> None:
        await super().stop()

    async def _on_output_value(self, value: DataPointValue) -> None:
        if not value.emit_outputs or value.float_value is None:
            return
        point = value.point_id.point
        address = point if point.startswith("/") else self._library_address_for_point(point)
        if address is None:
            address = point
        target = f"{self.name}:{address}"
        await self.adapter.send(
            MappedEvent(
                source="datapoint",
                target=target,
                value=value.float_value,
            )
        )
