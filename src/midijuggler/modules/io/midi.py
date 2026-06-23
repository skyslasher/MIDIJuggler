"""MIDI I/O module."""

from __future__ import annotations

import logging

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.migrate import effective_connections
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointId,
    DataPointValue,
    ValueType,
)
from midijuggler.device.points import MIDI_OUT_POINT, build_device_datapoints
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import DeviceConfig
from midijuggler.events import MidiMessageEvent
from midijuggler.midi.target_encode import encode_mapped_midi_target
from midijuggler.modules.base import IOModule

LOGGER = logging.getLogger(__name__)


class MidiIOModule(IOModule):
    """Send device data points to a bound MIDI adapter."""

    def __init__(
        self,
        adapter: MidiAdapter,
        device: DeviceConfig,
        store: DataPointStore,
        config: AppConfig,
        device_registry: DeviceRegistry,
    ) -> None:
        super().__init__(device.id, store)
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
        self.store.subscribe(
            DataPointId(self.name, MIDI_OUT_POINT),
            self._on_midi_out,
        )
        for point in self._output_points:
            self.store.subscribe(
                DataPointId(self.name, point),
                self._on_output_value,
            )
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
        for connection in connections:
            parsed = DataPointId.parse(connection.target)
            if parsed.module == self.name:
                targets.append(parsed)
        return targets

    async def stop(self) -> None:
        await super().stop()

    async def _on_midi_out(self, value: DataPointValue) -> None:
        if value.value_type != ValueType.MIDI_MESSAGE or value.midi_status is None:
            return
        await self.adapter.send_midi_message(
            MidiMessageEvent(
                source=self.adapter.name,
                status=value.midi_status,
                data=tuple(value.midi_data or ()),
                direction="output",
            )
        )

    async def _on_output_value(self, value: DataPointValue) -> None:
        if value.float_value is None:
            return
        self.adapter.remember_feedback_value(value.point_id.point, value.float_value)
        if not value.emit_outputs:
            return
        try:
            status, data = encode_mapped_midi_target(
                self.config,
                self.device_registry,
                self.name,
                value.point_id.point,
                value.float_value,
            )
        except ValueError:
            LOGGER.warning("unsupported MIDI output data point %s", value.point_id)
            return
        await self.adapter.send_midi_message(
            MidiMessageEvent(
                source=self.adapter.name,
                status=status,
                data=data,
                target=f"{self.adapter.name}:{value.point_id.point}",
                direction="output",
            )
        )
