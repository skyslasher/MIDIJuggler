"""Wing native I/O module."""

from __future__ import annotations

from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.migrate import effective_connections
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import ConnectionSpec, DataPointId, DataPointValue
from midijuggler.device.points import build_device_datapoints, library_address_for_point
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import DeviceConfig
from midijuggler.events import MappedEvent
from midijuggler.modules.base import IOModule
from midijuggler.modules.modifier.range_map import prefer_fader_unit_range


class WingNativeIOModule(IOModule):
    """Send device data points over the Wing native TCP protocol."""

    def __init__(
        self,
        adapter: WingNativeAdapter,
        device: DeviceConfig,
        store: DataPointStore,
        config: AppConfig,
        device_registry: DeviceRegistry,
    ) -> None:
        super().__init__(device.uid, store)
        self.adapter = adapter
        self.device = device
        self.config = config
        self.device_registry = device_registry
        adapter_config = device_registry.adapter_for_device(device.id)
        _, self._output_points = build_device_datapoints(device, adapter_config)

    def datapoints(self) -> list:
        adapter_config = self.device_registry.adapter_for_device(self.device.id)
        specs, output_points = build_device_datapoints(self.device, adapter_config)
        self._output_points = output_points
        return specs

    async def start(self) -> None:
        await super().start()
        self.adapter.clear_fader_output_ranges()
        connections = effective_connections(
            self.config,
            datapoint_routing=self.config.runtime.datapoint_routing,
        )
        fader_ranges: dict[str, tuple[float, float]] = {}
        for connection in connections:
            for address, range_min, range_max in self._connection_fader_unit_ranges(connection):
                fader_ranges[address] = prefer_fader_unit_range(
                    fader_ranges.get(address),
                    (range_min, range_max),
                )
        for address, (range_min, range_max) in fader_ranges.items():
            self.adapter.register_fader_output_range(address, range_min, range_max)
        for point in self._output_points:
            self.store.subscribe(DataPointId(self.name, point), self._on_output_value)
        for point_id in self._configured_output_targets():
            if point_id.point in self._output_points:
                continue
            self._output_points.add(point_id.point)
            self.store.subscribe(point_id, self._on_output_value)

    def _configured_output_targets(self) -> list[DataPointId]:
        connections = effective_connections(
            self.config,
            datapoint_routing=self.config.runtime.datapoint_routing,
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
        return library_address_for_point(self.device_registry, self.name, point)

    def _connection_fader_unit_ranges(
        self,
        connection: ConnectionSpec,
    ) -> list[tuple[str, float, float]]:
        ranges: list[tuple[str, float, float]] = []
        endpoints = (
            (DataPointId.parse(connection.source), connection.input_min, connection.input_max),
            (DataPointId.parse(connection.target), connection.output_min, connection.output_max),
        )
        for parsed, range_min, range_max in endpoints:
            if parsed.module != self.name:
                continue
            for point in (parsed.point, self._library_address_for_point(parsed.point)):
                if point is None:
                    continue
                address = point if point.startswith("/") else self._library_address_for_point(point)
                if address is None or "/fdr" not in address:
                    continue
                ranges.append((address, range_min, range_max))
        return ranges

    async def stop(self) -> None:
        await super().stop()

    async def _on_output_value(self, value: DataPointValue) -> None:
        if not value.emit_outputs or value.float_value is None:
            return
        point = value.point_id.point
        address = point if point.startswith("/") else self._library_address_for_point(point)
        if address is None:
            address = point
        target = f"{self.adapter.name}:{address}"
        await self.adapter.send(
            MappedEvent(
                source="datapoint",
                target=target,
                value=value.float_value,
            )
        )
