"""Master clock generator exposed as data points."""

from __future__ import annotations

import asyncio
import contextlib

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
    MasterClock,
    quantize_bpm,
)
from midijuggler.modules.base import GeneratorModule

CLOCK_MODULE = "clock"
BPM_EPSILON = 1e-6
BEAT_FLASH_DURATION_SECONDS = 0.12
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
        self._bpm_up_pressed = False
        self._bpm_down_pressed = False
        self._beat_off_task: asyncio.Task[None] | None = None

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
                category="bpm",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Master clock BPM",
                value_min=self.clock.config.bpm_min,
                value_max=self.clock.config.bpm_max,
                protocol="clock",
                category="bpm",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_up"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Increase BPM",
                protocol="clock",
                category="bpm",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_down"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Decrease BPM",
                protocol="clock",
                category="bpm",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "start"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Start transport",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "stop"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Stop transport",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "start_stop"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Toggle transport start/stop",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "tap_tempo"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Tap tempo on rising edge",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "running"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.INPUT,
                label="Transport running",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_tick"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI timing clock tick",
                protocol="clock",
                category="midi",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_start"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI transport start",
                protocol="clock",
                category="midi",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_continue"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI transport continue",
                protocol="clock",
                category="midi",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "midi_stop"),
                value_type=ValueType.MIDI_MESSAGE,
                direction=DataPointDirection.INPUT,
                label="MIDI transport stop",
                protocol="clock",
                category="midi",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "quarter_ms"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Quarter-note duration in ms",
                protocol="clock",
                category="timing",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "eighth_ms"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Eighth-note duration in ms",
                protocol="clock",
                category="timing",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "beat"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Beat flash pulse",
                value_min=0.0,
                value_max=1.0,
                protocol="clock",
                category="timing",
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
        await self._cancel_beat_off()
        await self.store.write(float_value(DataPointId(CLOCK_MODULE, "beat"), 0.0))
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
        if point == "bpm_up":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_bpm_up_pressed",
                on_rising=self._handle_bpm_up,
            )
            return
        if point == "bpm_down":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_bpm_down_pressed",
                on_rising=self._handle_bpm_down,
            )
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

    async def _handle_bpm_up(self, _value: DataPointValue) -> None:
        await self.clock.handle_command(
            MasterClockCommandEvent(
                source=CLOCK_MODULE,
                command="set_bpm",
                value=self._step_bpm(self.clock.config.bpm_step),
            )
        )
        asyncio.create_task(self._publish_outputs(), name="clock-publish-outputs")

    async def _handle_bpm_down(self, _value: DataPointValue) -> None:
        await self.clock.handle_command(
            MasterClockCommandEvent(
                source=CLOCK_MODULE,
                command="set_bpm",
                value=self._step_bpm(-self.clock.config.bpm_step),
            )
        )
        asyncio.create_task(self._publish_outputs(), name="clock-publish-outputs")

    def _step_bpm(self, delta: float) -> float:
        stepped = quantize_bpm(
            self.clock.bpm + delta,
            step=self.clock.config.bpm_quantize,
        )
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

    async def publish_beat(self) -> None:
        await self._cancel_beat_off()
        await self.store.write(float_value(DataPointId(CLOCK_MODULE, "beat"), 1.0))
        self._beat_off_task = asyncio.create_task(
            self._clear_beat_flash(),
            name="clock-beat-off",
        )

    async def _clear_beat_flash(self) -> None:
        try:
            await asyncio.sleep(BEAT_FLASH_DURATION_SECONDS)
            await self.store.write(float_value(DataPointId(CLOCK_MODULE, "beat"), 0.0))
        finally:
            self._beat_off_task = None

    async def _cancel_beat_off(self) -> None:
        if self._beat_off_task is None:
            return
        self._beat_off_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._beat_off_task
        self._beat_off_task = None

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
