"""Master clock generator exposed as data points."""

from __future__ import annotations

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ValueType,
    float_value,
    midi_message_value,
)
from midijuggler.events import MasterClockCommandEvent
from midijuggler.master_clock import MIDI_TIMING_CLOCK, MasterClock
from midijuggler.modules.base import GeneratorModule

CLOCK_MODULE = "clock"
BPM_EPSILON = 1e-6


class MasterClockGenerator(GeneratorModule):
    """Expose master-clock controls and outputs as data points."""

    def __init__(self, clock: MasterClock, store: DataPointStore) -> None:
        super().__init__(CLOCK_MODULE, store)
        self.clock = clock

    def datapoints(self) -> list[DataPointSpec]:
        return [
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_set"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Set master clock BPM",
                value_min=self.clock.config.bpm_min,
                value_max=self.clock.config.bpm_max,
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Master clock BPM",
                value_min=self.clock.config.bpm_min,
                value_max=self.clock.config.bpm_max,
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_up"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.INPUT,
                label="Increase BPM",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_down"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.INPUT,
                label="Decrease BPM",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "start"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.INPUT,
                label="Start transport",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "stop"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.INPUT,
                label="Stop transport",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "running"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.OUTPUT,
                label="Transport running",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_tick"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.OUTPUT,
                label="MIDI timing clock tick",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "quarter_ms"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Quarter-note duration in ms",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "eighth_ms"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Eighth-note duration in ms",
                protocol="clock",
            ),
        ]

    async def start(self) -> None:
        await super().start()
        for point in ("bpm_set", "bpm_up", "bpm_down", "start", "stop"):
            self.store.subscribe(
                DataPointId(CLOCK_MODULE, point),
                self._on_input,
            )
        await self._publish_outputs()

    async def stop(self) -> None:
        await super().stop()

    async def _on_input(self, value: DataPointValue) -> None:
        point = value.point_id.point
        if point == "bpm_set" and value.float_value is not None:
            if abs(value.float_value - self.clock.bpm) <= BPM_EPSILON:
                return
            await self.clock.handle_command(
                MasterClockCommandEvent(
                    source=CLOCK_MODULE,
                    command="set_bpm",
                    value=value.float_value,
                )
            )
            await self._publish_outputs()
            return
        if point == "bpm_up" and value.bool_value:
            step = max(1.0, self.clock.bpm * 0.01)
            await self.clock.handle_command(
                MasterClockCommandEvent(
                    source=CLOCK_MODULE,
                    command="set_bpm",
                    value=min(self.clock.config.bpm_max, self.clock.bpm + step),
                )
            )
            await self._publish_outputs()
            return
        if point == "bpm_down" and value.bool_value:
            step = max(1.0, self.clock.bpm * 0.01)
            await self.clock.handle_command(
                MasterClockCommandEvent(
                    source=CLOCK_MODULE,
                    command="set_bpm",
                    value=max(self.clock.config.bpm_min, self.clock.bpm - step),
                )
            )
            await self._publish_outputs()
            return
        if point == "start" and value.bool_value:
            if self.clock.running:
                return
            await self.clock.handle_command(
                MasterClockCommandEvent(source=CLOCK_MODULE, command="start")
            )
            await self._publish_outputs()
            return
        if point == "stop" and value.bool_value:
            if not self.clock.running:
                return
            await self.clock.handle_command(
                MasterClockCommandEvent(source=CLOCK_MODULE, command="stop")
            )
            await self._publish_outputs()

    async def publish_tick(self) -> None:
        await self.store.write(
            midi_message_value(DataPointId(CLOCK_MODULE, "midi_tick"), MIDI_TIMING_CLOCK)
        )

    async def _publish_outputs(self) -> None:
        await self.store.write(
            DataPointValue(
                point_id=DataPointId(CLOCK_MODULE, "running"),
                value_type=ValueType.BOOL,
                bool_value=self.clock.running,
            )
        )
        await self.store.write(float_value(DataPointId(CLOCK_MODULE, "bpm"), self.clock.bpm))
        controls = self.clock.parameters.as_controls()
        await self.store.write(
            float_value(DataPointId(CLOCK_MODULE, "quarter_ms"), controls["quarter_ms"])
        )
        await self.store.write(
            float_value(DataPointId(CLOCK_MODULE, "eighth_ms"), controls["eighth_ms"])
        )
