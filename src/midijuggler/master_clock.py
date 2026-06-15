"""MIDI master clock, remote control and optional audio click."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from midijuggler.click_player import ClickPlayer, create_click_player
from midijuggler.clock import MIDI_CLOCK_TICKS_PER_QUARTER
from midijuggler.config import MasterClockConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import (
    BpmChangedEvent,
    ClickEvent,
    ControlEvent,
    MasterClockCommandEvent,
    MasterClockStateEvent,
    MidiMessageEvent,
    OscMessageEvent,
)
from midijuggler.alsa import alsa_mode_for_device, MASTER_CLOCK_PCM_NAME

LOGGER = logging.getLogger(__name__)

MIDI_TIMING_CLOCK = 0xF8
MIDI_START = 0xFA
MIDI_CONTINUE = 0xFB
MIDI_STOP = 0xFC


class ClockDatapointSink(Protocol):
    async def publish_midi_message(self, status: int) -> None: ...


CLICK_INTERVAL_TICKS = {
    "eighth": MIDI_CLOCK_TICKS_PER_QUARTER // 2,
    "quarter": MIDI_CLOCK_TICKS_PER_QUARTER,
    "half": MIDI_CLOCK_TICKS_PER_QUARTER * 2,
    "whole": MIDI_CLOCK_TICKS_PER_QUARTER * 4,
}

TAP_TEMPO_RESET_TIMEOUT_SECONDS = 2.5
TAP_TEMPO_MAX_TAPS = 5
TAP_TEMPO_BPM_QUANTIZE_STEP = 0.5


def quantize_bpm(bpm: float, step: float = TAP_TEMPO_BPM_QUANTIZE_STEP) -> float:
    return round(bpm / step) * step


class TapTempoTracker:
    """Collect tap timestamps and derive BPM from recent intervals."""

    def __init__(
        self,
        *,
        reset_timeout: float = TAP_TEMPO_RESET_TIMEOUT_SECONDS,
        max_taps: int = TAP_TEMPO_MAX_TAPS,
        min_taps: int = 4,
    ) -> None:
        self.reset_timeout = reset_timeout
        self.max_taps = max_taps
        self.min_taps = min_taps
        self._tap_times: list[float] = []

    @property
    def tap_count(self) -> int:
        return len(self._tap_times)

    def register_tap(self, timestamp: float) -> float | None:
        if self._tap_times and timestamp - self._tap_times[-1] > self.reset_timeout:
            self._tap_times.clear()
        self._tap_times.append(timestamp)
        self._tap_times = self._tap_times[-self.max_taps :]
        if len(self._tap_times) < self.min_taps:
            return None
        intervals = [
            later - earlier
            for earlier, later in zip(self._tap_times, self._tap_times[1:], strict=False)
            if later > earlier
        ]
        if not intervals:
            return None
        return quantize_bpm(60.0 / (sum(intervals) / len(intervals)))

    def clear(self) -> None:
        self._tap_times.clear()


@dataclass(frozen=True)
class MasterClockParameters:
    """Derived time parameters for mappings and effect control."""

    bpm: float
    ppqn_tick_ms: float
    sixteenth_ms: float
    eighth_ms: float
    quarter_ms: float
    half_ms: float
    whole_ms: float
    bar_4_4_ms: float

    def as_controls(self) -> dict[str, float]:
        return {
            "bpm": self.bpm,
            "ppqn_tick_ms": self.ppqn_tick_ms,
            "sixteenth_ms": self.sixteenth_ms,
            "eighth_ms": self.eighth_ms,
            "quarter_ms": self.quarter_ms,
            "half_ms": self.half_ms,
            "whole_ms": self.whole_ms,
            "bar_4_4_ms": self.bar_4_4_ms,
        }


def bpm_to_parameters(bpm: float) -> MasterClockParameters:
    if bpm <= 0:
        raise ValueError("bpm must be > 0")
    quarter_ms = 60_000.0 / bpm
    return MasterClockParameters(
        bpm=bpm,
        ppqn_tick_ms=quarter_ms / MIDI_CLOCK_TICKS_PER_QUARTER,
        sixteenth_ms=quarter_ms / 4.0,
        eighth_ms=quarter_ms / 2.0,
        quarter_ms=quarter_ms,
        half_ms=quarter_ms * 2.0,
        whole_ms=quarter_ms * 4.0,
        bar_4_4_ms=quarter_ms * 4.0,
    )


class MasterClockRemote:
    """Translate OSC and MIDI controls into master-clock commands."""

    def __init__(self, config: MasterClockConfig) -> None:
        self.config = config
        self._pending_bpm_msb: int | None = None

    def command_from_osc(self, event: OscMessageEvent) -> MasterClockCommandEvent | None:
        if event.direction != "input" or not event.arguments:
            return None

        if event.address == self.config.bpm_osc_address:
            return MasterClockCommandEvent(
                source=event.source,
                command="set_bpm",
                value=float(event.arguments[0]),
            )

        if event.address == self.config.click_interval_osc_address:
            return MasterClockCommandEvent(
                source=event.source,
                command="set_click_interval",
                value=str(event.arguments[0]),
            )

        return None

    def command_from_midi(self, event: MidiMessageEvent) -> MasterClockCommandEvent | None:
        if event.direction != "input":
            return None

        status = event.status & 0xFF
        if status in {MIDI_START, MIDI_STOP, MIDI_CONTINUE}:
            return MasterClockCommandEvent(
                source=event.source,
                command={
                    MIDI_START: "start",
                    MIDI_STOP: "stop",
                    MIDI_CONTINUE: "continue",
                }[status],
            )

        if not _is_control_change_on_channel(status, self.config.midi_channel):
            return None
        if len(event.data) < 2:
            return None

        controller = event.data[0] & 0x7F
        value = event.data[1] & 0x7F
        if controller == self.config.bpm_msb_cc:
            self._pending_bpm_msb = value
            return None
        if controller == self.config.bpm_lsb_cc and self._pending_bpm_msb is not None:
            raw = (self._pending_bpm_msb << 7) | value
            return MasterClockCommandEvent(
                source=event.source,
                command="set_bpm",
                value=_scale_14bit(raw, self.config.bpm_min, self.config.bpm_max),
            )
        if controller == self.config.click_interval_cc:
            return MasterClockCommandEvent(
                source=event.source,
                command="set_click_interval",
                value=_click_interval_from_midi_value(value),
            )

        return None


class MasterClock:
    """Generate MIDI timing clock and optional click from local BPM state."""

    def __init__(
        self,
        config: MasterClockConfig,
        bus: EventBus,
        click_player: ClickPlayer | None = None,
        click_audio_device: str | None = None,
        alsa_config_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.bpm = config.bpm
        self.click_interval = config.click_interval
        self.running = False
        self.position_ticks = 0
        self.remote = MasterClockRemote(config)
        self.click_audio_device = click_audio_device
        self.alsa_config_path = Path(alsa_config_path) if alsa_config_path is not None else None
        self.click_player = click_player or self._build_click_player(config)
        self._transport_task: asyncio.Task[None] | None = None
        self._click_tasks: set[asyncio.Task[None]] = set()
        self._datapoint_sink: ClockDatapointSink | None = None
        self._tap_tempo = TapTempoTracker(min_taps=config.tap_tempo_min_taps)

    def bind_datapoint_sink(self, sink: ClockDatapointSink | None) -> None:
        self._datapoint_sink = sink

    @property
    def parameters(self) -> MasterClockParameters:
        return bpm_to_parameters(self.bpm)

    @property
    def tap_count(self) -> int:
        return self._tap_tempo.tap_count

    async def start(self) -> None:
        await self._publish_state()
        await self._publish_parameters()
        if self.config.enabled and self.config.auto_start:
            await self.start_transport(reset_position=True)

    async def stop(self) -> None:
        await self.stop_transport(send_transport=False)
        await self.click_player.close()

    async def configure(self, config: MasterClockConfig) -> None:
        """Apply a new master-clock configuration at runtime."""

        was_running = self.running
        if was_running and not config.enabled:
            await self.stop_transport(send_transport=config.send_transport)

        self.config = config
        self.remote = MasterClockRemote(config)
        self._tap_tempo.min_taps = config.tap_tempo_min_taps
        await self._replace_click_player(config)
        self.bpm = config.bpm
        self.click_interval = config.click_interval

        if config.enabled and config.auto_start and not self.running:
            await self.start_transport(reset_position=True)
        else:
            await self.bus.publish(BpmChangedEvent(source="master_clock", bpm=self.bpm))
            await self._publish_state()
            await self._publish_parameters()

    async def handle_command(self, event: MasterClockCommandEvent) -> None:
        if event.command == "set_bpm":
            await self.set_bpm(float(event.value))
        elif event.command == "set_click_interval":
            await self.set_click_interval(str(event.value))
        elif event.command == "start":
            if self.running:
                return
            await self.start_transport(reset_position=True)
        elif event.command == "continue":
            await self.continue_transport()
        elif event.command == "stop":
            await self.stop_transport()

    async def handle_osc_message(self, event: OscMessageEvent) -> None:
        command = self.remote.command_from_osc(event)
        if command is not None:
            await self.handle_command(command)

    async def handle_midi_message(self, event: MidiMessageEvent) -> None:
        command = self.remote.command_from_midi(event)
        if command is not None:
            await self.handle_command(command)

    async def set_bpm(self, bpm: float) -> None:
        if not self.config.bpm_min <= bpm <= self.config.bpm_max:
            raise ValueError(
                f"bpm must be between {self.config.bpm_min} and {self.config.bpm_max}"
            )
        if abs(self.bpm - bpm) <= 1e-6:
            return
        self.bpm = bpm
        self.config = replace(self.config, bpm=bpm)
        self.remote = MasterClockRemote(self.config)
        await self.bus.publish(BpmChangedEvent(source="master_clock", bpm=bpm))
        await self._publish_state()
        await self._publish_parameters()

    async def set_click_interval(self, interval: str) -> None:
        if interval not in CLICK_INTERVAL_TICKS:
            raise ValueError("click interval must be eighth, quarter, half or whole")
        self.click_interval = interval
        await self._publish_state()

    async def start_transport(self, reset_position: bool) -> None:
        was_running = self.running
        if reset_position and not was_running:
            self.position_ticks = 0
        self.running = True
        if self.config.send_transport and not was_running:
            await self._publish_midi_status(MIDI_START)
        self._ensure_transport_task()
        await self._publish_state()

    async def continue_transport(self) -> None:
        self.running = True
        if self.config.send_transport:
            await self._publish_midi_status(MIDI_CONTINUE)
        self._ensure_transport_task()
        await self._publish_state()

    async def stop_transport(self, send_transport: bool = True) -> None:
        self.running = False
        await self._cancel_transport_task()
        if send_transport and self.config.send_transport:
            await self._publish_midi_status(MIDI_STOP)
        await self._publish_state()

    async def toggle_transport(self) -> None:
        if self.running:
            await self.stop_transport()
        else:
            await self.start_transport(reset_position=True)

    async def register_tap_tempo(self, timestamp: float | None = None) -> float | None:
        """Record a tap on the rising edge and update BPM when enough taps exist."""

        bpm = self._tap_tempo.register_tap(
            time.monotonic() if timestamp is None else timestamp
        )
        if bpm is None:
            return None
        clamped = min(max(bpm, self.config.bpm_min), self.config.bpm_max)
        await self.set_bpm(clamped)
        return clamped

    async def emit_tick(self) -> None:
        """Emit one MIDI clock tick. Exposed for tests and deterministic stepping."""

        await self._emit_frame()

    def _ensure_transport_task(self) -> None:
        if self._transport_task is None or self._transport_task.done():
            self._transport_task = asyncio.create_task(
                self._run_transport(),
                name="master-clock",
            )

    async def _cancel_transport_task(self) -> None:
        if self._transport_task is None:
            return
        self._transport_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._transport_task
        self._transport_task = None

    async def _emit_frame(self) -> None:
        if self._is_click_tick(self.position_ticks):
            await self._emit_click()
        await self._emit_midi_tick()

    async def _emit_midi_tick(self) -> None:
        await self._publish_midi_status(MIDI_TIMING_CLOCK)
        self.position_ticks += 1

    async def _emit_click(self) -> None:
        if self.config.click_enabled:
            self._trigger_click()
        await self.bus.publish(
            ClickEvent(
                source="master_clock",
                interval=self.click_interval,
                position_ticks=self.position_ticks,
            )
        )

    async def _sleep_frame(self) -> None:
        if not self.running:
            return
        await asyncio.sleep(self._seconds_per_tick())

    async def _replace_click_player(self, config: MasterClockConfig) -> None:
        previous = self.click_player
        self.click_player = self._build_click_player(config)
        if previous is not None:
            await previous.close()

    def _build_click_player(self, config: MasterClockConfig) -> ClickPlayer:
        playback_device = self.click_audio_device or config.click_audio_device
        environment = (
            {"ALSA_CONFIG_PATH": str(self.alsa_config_path)}
            if self.alsa_config_path is not None
            else None
        )
        return create_click_player(
            config.click_wav,
            command=config.click_command,
            audio_device=playback_device,
            environment=environment,
            allow_overlap=self._click_player_allows_overlap(config, playback_device),
        )

    def _click_player_allows_overlap(
        self,
        config: MasterClockConfig,
        playback_device: str,
    ) -> bool:
        if playback_device == MASTER_CLOCK_PCM_NAME:
            return True
        configured_device = config.click_audio_device or playback_device
        if not configured_device:
            return False
        return alsa_mode_for_device(configured_device) == "dmix"

    def _trigger_click(self) -> None:
        task = asyncio.create_task(self.click_player.play(), name="click-trigger")
        self._click_tasks.add(task)
        task.add_done_callback(self._click_tasks.discard)

    async def _run_transport(self) -> None:
        try:
            while self.running:
                await self._emit_frame()
                await self._sleep_frame()
        except asyncio.CancelledError:
            raise

    def _seconds_per_tick(self) -> float:
        return 60.0 / (self.bpm * MIDI_CLOCK_TICKS_PER_QUARTER)

    def _is_click_tick(self, frame: int) -> bool:
        return frame % CLICK_INTERVAL_TICKS[self.click_interval] == 0

    async def _publish_midi_status(self, status: int) -> None:
        if self._datapoint_sink is not None:
            await self._datapoint_sink.publish_midi_message(status)
            return
        targets = self.config.output_targets or [""]
        for target in targets:
            await self.bus.publish(
                MidiMessageEvent(
                    source="master_clock",
                    direction="output",
                    target=target,
                    status=status,
                )
            )

    async def _publish_state(self) -> None:
        await self.bus.publish(
            MasterClockStateEvent(
                source="master_clock",
                bpm=self.bpm,
                running=self.running,
                position_ticks=self.position_ticks,
                click_interval=self.click_interval,
            )
        )

    async def _publish_parameters(self) -> None:
        for control, value in self.parameters.as_controls().items():
            await self.bus.publish(
                ControlEvent(source="clock", control=control, value=value)
            )


def _is_control_change_on_channel(status: int, channel: int) -> bool:
    if not 1 <= channel <= 16:
        return False
    return status == 0xB0 + (channel - 1)


def _scale_14bit(raw: int, minimum: float, maximum: float) -> float:
    clamped = min(max(raw, 0), 16_383)
    return minimum + (clamped / 16_383.0) * (maximum - minimum)


def _click_interval_from_midi_value(value: int) -> str:
    if value < 32:
        return "eighth"
    if value < 64:
        return "quarter"
    if value < 96:
        return "half"
    return "whole"
