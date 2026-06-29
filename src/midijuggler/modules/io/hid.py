"""HID I/O module."""

from __future__ import annotations

from midijuggler.adapters.hid import HidAdapter
from midijuggler.datapoint.store import DataPointStore
from midijuggler.device.points import build_device_datapoints
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import DeviceConfig
from midijuggler.modules.base import IOModule


class HidIOModule(IOModule):
    """Expose configured HID controls as device input data points."""

    def __init__(
        self,
        adapter: HidAdapter,
        device: DeviceConfig,
        store: DataPointStore,
        device_registry: DeviceRegistry,
    ) -> None:
        super().__init__(device.uid, store)
        self.adapter = adapter
        self.device = device
        self.device_registry = device_registry

    def datapoints(self) -> list:
        adapter_config = self.device_registry.adapter_for_device(self.device.id)
        specs, _output_points = build_device_datapoints(
            self.device,
            adapter_config,
            hid_adapter=self.adapter,
        )
        return specs

    async def start(self) -> None:
        await super().start()

    async def stop(self) -> None:
        await super().stop()
