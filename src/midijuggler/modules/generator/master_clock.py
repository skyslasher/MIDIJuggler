"""Master clock generator exposed as data points."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

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
    click_interval_from_set_value,
    click_interval_to_set_value,
    next_click_interval,
    quantize_bpm,
)
from midijuggler.modules.base import GeneratorModule

CLOCK_MODULE = "clock"
BPM_EPSILON = 1e-6
BEAT_FLASH_INTERVAL_RATIO = 0.45
BEAT_INTERVAL_MS_KEYS = {
    "sixteenth": "sixteenth_ms",
    "eighth": "eighth_ms",
    "quarter": "quarter_ms",
    "half": "half_ms",
    "whole": "whole_ms",
}
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
        self._bpm_huge_up_pressed = False
        self._bpm_huge_down_pressed = False
        self._click_toggle_pressed = False
        self._click_interval_cycle_pressed = False
        self._beat_off_task: asyncio.Task[None] | None = None
        self._beat_publish_lock = asyncio.Lock()
        self._beat_pulse_generation = 0

    async def publish_outputs(self) -> None:
        await self._publish_outputs()

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
                id=DataPointId(CLOCK_MODULE, "bpm_huge_up"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Huge increase BPM",
                protocol="clock",
                category="bpm",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "bpm_huge_down"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Huge decrease BPM",
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
                id=DataPointId(CLOCK_MODULE, "click_set"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.OUTPUT,
                label="Set audio click enabled",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "click_toggle"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Toggle audio click enabled",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "click_interval_set"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Set click/beat interval (0=whole .. 4=sixteenth)",
                value_min=0.0,
                value_max=4.0,
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "click_interval_cycle"),
                value_type=ValueType.TRIGGER,
                direction=DataPointDirection.OUTPUT,
                label="Cycle click/beat interval",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "click_enabled"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.INPUT,
                label="Audio click enabled",
                protocol="clock",
                category="transport",
            ),
            DataPointSpec(
                id=DataPointId(CLOCK_MODULE, "click_interval"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Click/beat interval (0=whole .. 4=sixteenth)",
                value_min=0.0,
                value_max=4.0,
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
            "bpm_huge_up",
            "bpm_huge_down",
            "start",
            "stop",
            "start_stop",
            "tap_tempo",
            "click_set",
            "click_toggle",
            "click_interval_set",
            "click_interval_cycle",
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
            if abs(value.float_value - self.clock.bpm) > BPM_EPSILON:
                await self.clock.handle_command(
                    MasterClockCommandEvent(
                        source=CLOCK_MODULE,
                        command="set_bpm",
                        value=value.float_value,
                    )
                )
            await self._publish_outputs(force_bpm=True)
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
        if point == "bpm_huge_up":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_bpm_huge_up_pressed",
                on_rising=self._handle_bpm_huge_up,
            )
            return
        if point == "bpm_huge_down":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_bpm_huge_down_pressed",
                on_rising=self._handle_bpm_huge_down,
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
            return
        if point == "click_set":
            if value.bool_value is None and value.float_value is None:
                return
            enabled = value_is_active(value)
            await self.clock.set_click_enabled(enabled)
            await self._publish_outputs()
            return
        if point == "click_toggle":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_click_toggle_pressed",
                on_rising=self._toggle_click,
            )
            return
        if point == "click_interval_set" and value.float_value is not None:
            interval = click_interval_from_set_value(value.float_value)
            if interval == self.clock.click_interval:
                return
            await self.clock.handle_command(
                MasterClockCommandEvent(
                    source=CLOCK_MODULE,
                    command="set_click_interval",
                    value=interval,
                )
            )
            await self._publish_outputs()
            return
        if point == "click_interval_cycle":
            await self._handle_trigger_edge(
                value,
                pressed_attr="_click_interval_cycle_pressed",
                on_rising=self._cycle_click_interval,
            )

    async def _cycle_click_interval(self, _value: DataPointValue) -> None:
        interval = next_click_interval(self.clock.click_interval)
        await self.clock.handle_command(
            MasterClockCommandEvent(
                source=CLOCK_MODULE,
                command="set_click_interval",
                value=interval,
            )
        )
        await self._publish_outputs()

    async def _toggle_click(self, _value: DataPointValue) -> None:
        await self.clock.toggle_click_enabled()
        await self._publish_outputs()

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

    async def _handle_bpm_huge_up(self, _value: DataPointValue) -> None:
        await self.clock.handle_command(
            MasterClockCommandEvent(
                source=CLOCK_MODULE,
                command="set_bpm",
                value=self._step_bpm(self.clock.config.bpm_huge_step),
            )
        )
        asyncio.create_task(self._publish_outputs(), name="clock-publish-outputs")

    async def _handle_bpm_huge_down(self, _value: DataPointValue) -> None:
        await self.clock.handle_command(
            MasterClockCommandEvent(
                source=CLOCK_MODULE,
                command="set_bpm",
                value=self._step_bpm(-self.clock.config.bpm_huge_step),
            )
        )
        asyncio.create_task(self._publish_outputs(), name="clock-publish-outputs")

    def _step_bpm(self, delta: float) -> float:
        stepped = quantize_bpm(
            self.clock.bpm + delta,
            step=TAP_TEMPO_BPM_QUANTIZE_STEP,
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
        async with self._beat_publish_lock:
            await self._cancel_beat_off()
            self._beat_pulse_generation += 1
            generation = self._beat_pulse_generation
            flash_seconds = self._effective_beat_flash_seconds()

        point = DataPointId(CLOCK_MODULE, "beat")
        current = self.store.float_value(point)
        if current is not None and current > 0.5:
            await self.store.write(float_value(point, 0.0, force_notify=True))
        await self.store.write(float_value(point, 1.0, force_notify=True))

        async with self._beat_publish_lock:
            if generation != self._beat_pulse_generation:
                return
            self._beat_off_task = asyncio.create_task(
                self._clear_beat_flash(generation, flash_seconds),
                name="clock-beat-off",
            )

    def trigger_beat_pulse(self) -> None:
        """Schedule clock.beat publish from the transport thread at click-tick time."""

        loop = self.clock._asyncio_loop
        if loop is None or loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(self.publish_beat(), loop)
        future.add_done_callback(self._log_scheduled_beat_result)

    @staticmethod
    def _log_scheduled_beat_result(future: asyncio.Future[Any]) -> None:
        with contextlib.suppress(Exception):
            future.result()

    def _beat_interval_ms(self) -> float:
        key = BEAT_INTERVAL_MS_KEYS.get(
            self.clock.click_interval,
            "quarter_ms",
        )
        return self.clock.parameters.as_controls()[key]

    def _effective_beat_flash_seconds(self) -> float:
        configured_ms = self.clock.config.beat_flash_ms
        interval_ms = self._beat_interval_ms()
        effective_ms = min(configured_ms, interval_ms * BEAT_FLASH_INTERVAL_RATIO)
        return max(effective_ms, 1.0) / 1000.0

    async def _clear_beat_flash(self, generation: int, duration_seconds: float) -> None:
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(duration_seconds)
            async with self._beat_publish_lock:
                if generation != self._beat_pulse_generation:
                    return
            await self.store.write(
                float_value(DataPointId(CLOCK_MODULE, "beat"), 0.0, force_notify=True)
            )
        finally:
            async with self._beat_publish_lock:
                if self._beat_off_task is current_task:
                    self._beat_off_task = None

    async def _cancel_beat_off(self) -> None:
        if self._beat_off_task is None:
            return
        self._beat_off_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._beat_off_task
        self._beat_off_task = None

    async def _publish_outputs(self, *, force_bpm: bool = False) -> None:
        await self.store.write(
            DataPointValue(
                point_id=DataPointId(CLOCK_MODULE, "running"),
                value_type=ValueType.BOOL,
                bool_value=self.clock.running,
            )
        )
        await self.store.write(
            DataPointValue(
                point_id=DataPointId(CLOCK_MODULE, "click_enabled"),
                value_type=ValueType.BOOL,
                bool_value=self.clock.config.click_enabled,
            )
        )
        await self.store.write(
            float_value(
                DataPointId(CLOCK_MODULE, "click_interval"),
                click_interval_to_set_value(self.clock.click_interval),
            )
        )
        await self.store.write(
            float_value(
                DataPointId(CLOCK_MODULE, "bpm"),
                self.clock.bpm,
                force_notify=force_bpm,
            )
        )
        await self.store.write(
            float_value(
                DataPointId(CLOCK_MODULE, "bpm_set"),
                self.clock.bpm,
                emit_outputs=False,
            )
        )
        controls = self.clock.parameters.as_controls()
        await self.store.write(
            float_value(DataPointId(CLOCK_MODULE, "quarter_ms"), controls["quarter_ms"])
        )
        await self.store.write(
            float_value(DataPointId(CLOCK_MODULE, "eighth_ms"), controls["eighth_ms"])
        )
