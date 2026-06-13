"""MIDI I/O module."""

from __future__ import annotations

import logging

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.bridge import legacy_target_to_datapoint
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
from midijuggler.midi.target_encode import encode_midi_target_message, resolve_midi_target_parameter
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

    async def stop(self) -> None:
        await super().stop()

    async def _on_output_value(self, value: DataPointValue) -> None:
        if value.float_value is None:
            return
        try:
            parameter = resolve_midi_target_parameter(
                self.config,
                self.name,
                value.point_id.point,
            )
            status, data = encode_midi_target_message(parameter, value.float_value)
        except ValueError:
            await self._send_legacy_target(value)
            return
        await self.adapter.send_midi_message(
            MidiMessageEvent(
                source=self.name,
                status=status,
                data=data,
                target=f"{self.name}:{value.point_id.point}",
                direction="output",
            )
        )

    async def _send_legacy_target(self, value: DataPointValue) -> None:
        point = value.point_id.point
        if not point.startswith("cc_") or value.float_value is None:
            LOGGER.warning("unsupported MIDI output data point %s", value.point_id)
            return
        parts = point.split("_")
        if len(parts) != 3:
            return
        channel = int(parts[1])
        controller = int(parts[2])
        scaled = max(0, min(127, int(round(value.float_value))))
        await self.adapter.send_midi_message(
            MidiMessageEvent(
                source=self.name,
                status=0xB0 | (channel & 0x0F),
                data=(controller, scaled),
                target=f"{self.name}:{point}",
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
