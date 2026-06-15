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
    value_is_active,
)
from midijuggler.events import MasterClockCommandEvent
from midijuggler.master_clock import (
    MIDI_CONTINUE,
    MIDI_START,
    MIDI_STOP,
    MIDI_TIMING_CLOCK,
    TAP_TEMPO_BPM_QUANTIZE_STEP,
    MasterClock,
    quantize_bpm,
)
from midijuggler.modules.base import GeneratorModule

CLOCK_MODULE = "clock"
BPM_EPSILON = 1e-6
CLOCK_MIDI_OUTPUT_POINTS = {
    MIDI_TIMING_CLOCK: "midi_tick",
    MIDI_START: "midi_start",
    MIDI_CONTINUE: "midi_continue",
    MIDI_STOP: "midi_stop",
}


class MasterClockGenerator(GeneratorModule):
    """Expose master-clock controls and outputs as data points."""

    def __init__(self, clock: MasterClock, store: DataPointStore) -> None:
        super().__init__(CLOCK_MODULE, store)
        self.clock = clock
        self._tap_tempo_pressed = False
        self._start_stop_pressed = False

    def datapoints(self) -> list[DataPointSpec]:
        return [
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_set"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Set master clock BPM",
                value_min=self.clock.config.bpm_min,
                value_max=self.clock.config.bpm_max,
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Master clock BPM",
                value_min=self.clock.config.bpm_min,
                value_max=self.clock.config.bpm_max,
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_up"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Increase BPM",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_down"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Decrease BPM",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "start"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Start transport",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "stop"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Stop transport",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "start_stop"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Toggle transport start/stop",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "tap_tempo"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Tap tempo on rising edge",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "running"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.INPUT,
                label="Transport running",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_tick"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI timing clock tick",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_start"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI transport start",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_continue"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI transport continue",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_stop"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI transport stop",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "quarter_ms"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Quarter-note duration in ms",
                protocol="clock",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "eighth_ms"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Eighth-note duration in ms",
                protocol="clock",
            ),
        ]

    async def start(self) -> None:
        await super().start()
        for point in (
            "bpm_set",
            "bpm_up",
            "bpm_down",
            "start",
            "stop",
            "start_stop",
            "tap_tempo",
        ):
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
        if point == "bpm_up" and value_is_active(value):
            await self.clock.handle_command(
                MasterClockCommandEvent(
                    source=CLOCK_MODULE,
                    command="set_bpm",
                    value=self._step_bpm(TAP_TEMPO_BPM_QUANTIZE_STEP),
                )
            )
            await self._publish_outputs()
            return
        if point == "bpm_down" and value_is_active(value):
            await self.clock.handle_command(
                MasterClockCommandEvent(
                    source=CLOCK_MODULE,
                    command="set_bpm",
                    value=self._step_bpm(-TAP_TEMPO_BPM_QUANTIZE_STEP),
                )
            )
            await self._publish_outputs()
            return
        if point == "start" and value_is_active(value):
            if self.clock.running:
                return
            await self.clock.handle_command(
                MasterClockCommandEvent(source=CLOCK_MODULE, command="start")
            )
            await self._publish_outputs()
            return
        if point == "stop" and value_is_active(value):
            if not self.clock.running:
                return
            await self.clock.handle_command(
                MasterClockCommandEvent(source=CLOCK_MODULE, command="stop")
            )
            await self._publish_outputs()
            return
        if point == "start_stop":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_start_stop_pressed",
                on_rising=self._toggle_transport,
            )
            return
        if point == "tap_tempo":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_tap_tempo_pressed",
                on_rising=self._register_tap_tempo,
            )

    async def _toggle_transport(self, _value: DataPointValue) -> None:
        await self.clock.toggle_transport()
        await self._publish_outputs()

    def _step_bpm(self, delta: float) -> float:
        stepped = quantize_bpm(self.clock.bpm + delta)
        return min(
            max(stepped, self.clock.config.bpm_min),
            self.clock.config.bpm_max,
        )

    async def _register_tap_tempo(self, value: DataPointValue) -> None:
        await self.clock.register_tap_tempo(value.timestamp)
        await self._publish_outputs()

    async def _handle_trigger_edge(
        self,
        value: DataPointValue,
        *,
        pressed_attr: str,
        on_rising,
    ) -> None:
        active = value_is_active(value)
        was_pressed = getattr(self, pressed_attr)
        setattr(self, pressed_attr, active)
        if active and not was_pressed:
            await on_rising(value)

    async def publish_tick(self) -> None:
        await self.publish_midi_message(MIDI_TIMING_CLOCK)

    async def publish_midi_message(self, status: int) -> None:
        point = CLOCK_MIDI_OUTPUT_POINTS.get(status & 0xFF)
        if point is None:
            return
        await self.store.write(
            midi_message_value(DataPointId(CLOCK_MODULE, point), status & 0xFF)
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
