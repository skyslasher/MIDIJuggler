"""MIDI I/O module."""

from __future__ import annotations

import logging

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.bridge import connections_from_legacy_mappings, legacy_target_to_datapoint
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ValueType,
    float_value,
)
from midijuggler.events import MappedEvent, MidiMessageEvent
from midijuggler.mapping import MappingRule
from midijuggler.midi.library_match import resolve_library_port
from midijuggler.midi.target_encode import encode_mapped_midi_target
from midijuggler.midi_library import get_midi_library
from midijuggler.modules.base import IOModule

LOGGER = logging.getLogger(__name__)


class MidiIOModule(IOModule):
    """Expose MIDI library parameters and raw controls as data points."""

    def __init__(
        self,
        adapter: MidiAdapter,
        store: DataPointStore,
        config: AppConfig,
    ) -> None:
        super().__init__(adapter.name, store)
        self.adapter = adapter
        self.config = config
        self._output_points: set[str] = set()

    def datapoints(self) -> list[DataPointSpec]:
        specs: list[DataPointSpec] = []
        library_id = str(self.adapter.config.options.get("midi_library", "")).strip()
        if library_id:
            try:
                library = get_midi_library(library_id)
            except KeyError:
                library = None
            if library is not None:
                library_port = resolve_library_port(self.adapter.config)
                for parameter in library.parameters:
                    direction = (
                        DataPointDirection.INPUT
                        if parameter.direction == "source"
                        else DataPointDirection.OUTPUT
                    )
                    specs.append(
                        DataPointSpec(
                            id=DataPointId(self.name, parameter.id),
                            value_type=ValueType.FLOAT,
                            direction=direction,
                            label=parameter.label,
                            value_min=float(parameter.value_min),
                            value_max=float(parameter.value_max),
                            protocol="midi",
                        )
                    )
                    if direction == DataPointDirection.OUTPUT:
                        self._output_points.add(parameter.id)
        return specs

    async def start(self) -> None:
        await super().start()
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
        connections = list(self.config.connections)
        if not connections:
            connections = connections_from_legacy_mappings(self.config.mappings)
        targets: list[DataPointId] = []
        for connection in connections:
            parsed = DataPointId.parse(connection.target)
            if parsed.module == self.name:
                targets.append(parsed)
        return targets

    async def stop(self) -> None:
        await super().stop()

    async def _on_output_value(self, value: DataPointValue) -> None:
        if value.float_value is None:
            return
        try:
            status, data = encode_mapped_midi_target(
                self.config,
                self.name,
                value.point_id.point,
                value.float_value,
            )
        except ValueError:
            LOGGER.warning("unsupported MIDI output data point %s", value.point_id)
            return
        self.adapter.remember_feedback_value(value.point_id.point, value.float_value)
        await self.adapter.send_midi_message(
            MidiMessageEvent(
                source=self.name,
                status=status,
                data=data,
                target=f"{self.name}:{value.point_id.point}",
                direction="output",
            )
        )

    async def send_mapped_event(self, event: MappedEvent) -> None:
        point_id = _mapped_target_to_point_id(event.target)
        if point_id is None:
            return
        await self.store.write(float_value(point_id, event.value))

    async def apply_mapping_output(self, rule: MappingRule, value: float) -> None:
        point_id = DataPointId.parse(legacy_target_to_datapoint(rule.target))
        await self.store.write(float_value(point_id, value))


def _mapped_target_to_point_id(target: str) -> DataPointId | None:
    module, separator, point = target.partition(":")
    if not separator:
        return None
    if point.startswith("cc:"):
        parts = point.split(":")
        if len(parts) == 3:
            channel = int(parts[1]) - 1
            controller = int(parts[2])
            return DataPointId(module, f"cc_{channel}_{controller}")
    if not point.startswith(("cc_", "note_", "program_")):
        return DataPointId(module, point.replace(":", "_"))
    return DataPointId(module, point)
