"""OSC I/O module."""

from __future__ import annotations

import logging

from midijuggler.adapters.osc import OscAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointId, DataPointValue
from midijuggler.device.points import build_device_datapoints
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import DeviceConfig
from midijuggler.events import MappedEvent
from midijuggler.modules.base import IOModule

LOGGER = logging.getLogger(__name__)


class OscIOModule(IOModule):
    """Send device data points to a bound OSC adapter."""

    def __init__(
        self,
        adapter: OscAdapter,
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
        for point in self._output_points:
            self.store.subscribe(DataPointId(self.name, point), self._on_output_value)

    async def stop(self) -> None:
        await super().stop()

    async def _on_output_value(self, value: DataPointValue) -> None:
        if not value.emit_outputs or value.float_value is None:
            return
        target = f"{self.adapter.name}:{value.point_id.point}"
        await self.adapter.send(
            MappedEvent(
                source="datapoint",
                target=target,
                value=value.float_value,
            )
        )
