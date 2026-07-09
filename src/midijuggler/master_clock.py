"""MIDI master clock, remote control and optional audio click."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from midijuggler.alsa import MASTER_CLOCK_PCM_NAME, alsa_mode_for_device, is_wing_routing_pcm, master_clock_playback_target
from midijuggler.click_player import ClickPlayer, _try_set_realtime_priority, create_click_player
from midijuggler.clock import CLICK_INTERVALS, MIDI_CLOCK_TICKS_PER_QUARTER
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

LOGGER = logging.getLogger(__name__)

MIDI_TIMING_CLOCK = 0xF8

# Timing parameters exposed on the event bus and as connection data points.
CLOCK_BUS_CONTROL_PUBLISH = frozenset({"bpm", "quarter_ms", "eighth_ms"})
MIDI_START = 0xFA
MIDI_CONTINUE = 0xFB
MIDI_STOP = 0xFC


BeatPulseListener = Callable[[], None]


class ClockDatapointSink(Protocol):
    async def publish_midi_message(self, status: int) -> None: ...

    async def publish_beat(self) -> None: ...

    def trigger_beat_pulse(self) -> None: ...

    async def publish_outputs(self) -> None: ...


CLICK_INTERVAL_TICKS = {
    "sixteenth": MIDI_CLOCK_TICKS_PER_QUARTER // 4,
    "eighth": MIDI_CLOCK_TICKS_PER_QUARTER // 2,
    "quarter": MIDI_CLOCK_TICKS_PER_QUARTER,
    "half": MIDI_CLOCK_TICKS_PER_QUARTER * 2,
    "whole": MIDI_CLOCK_TICKS_PER_QUARTER * 4,
}


def click_interval_from_set_value(value: float) -> str:
    """Map a connection float (0..4) to a named click interval (0=whole .. 4=sixteenth)."""

    index = int(round(value))
    index = max(0, min(index, len(CLICK_INTERVALS) - 1))
    return CLICK_INTERVALS[len(CLICK_INTERVALS) - 1 - index]


def click_interval_to_set_value(interval: str) -> float:
    """Map a named click interval to the connection float (0=whole .. 4=sixteenth)."""

    if interval not in CLICK_INTERVALS:
        interval = "quarter"
    index = CLICK_INTERVALS.index(interval)
    return float(len(CLICK_INTERVALS) - 1 - index)


def next_click_interval(current: str) -> str:
    if current not in CLICK_INTERVALS:
        return CLICK_INTERVALS[2]
    index = CLICK_INTERVALS.index(current)
    return CLICK_INTERVALS[(index + 1) % len(CLICK_INTERVALS)]

TAP_TEMPO_RESET_TIMEOUT_SECONDS = 2.5
TAP_TEMPO_MAX_TAPS = 5
TAP_TEMPO_BPM_QUANTIZE_STEP = 1.0


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
        quantize_step: float = TAP_TEMPO_BPM_QUANTIZE_STEP,
    ) -> None:
        self.reset_timeout = reset_timeout
        self.max_taps = max_taps
        self.min_taps = min_taps
        self.quantize_step = quantize_step
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
        return quantize_bpm(
            60.0 / (sum(intervals) / len(intervals)),
            step=self.quantize_step,
        )

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
        if event.direction != "input":
            return None

        if event.address == self.config.start_stop_osc_address:
            return MasterClockCommandEvent(
                source=event.source,
                command="start_stop",
                value=1.0,
            )

        if event.address == self.config.click_toggle_osc_address:
            return MasterClockCommandEvent(
                source=event.source,
                command="toggle_click",
                value=1.0,
            )

        if event.address == "/midijuggler/clock/tap_tempo":
            return MasterClockCommandEvent(
                source=event.source,
                command="tap_tempo",
                value=1.0,
            )

        if not event.arguments:
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
        self._asyncio_loop: asyncio.AbstractEventLoop | None = None
        self._transport_thread: threading.Thread | None = None
        self._transport_stop_event = threading.Event()
        self._bpm_notify_task: asyncio.Task[None] | None = None
        self._click_tasks: set[asyncio.Task[None]] = set()
        self._datapoint_sink: ClockDatapointSink | None = None
        self._beat_pulse_listeners: list[BeatPulseListener] = []
        self._tap_tempo = TapTempoTracker(
            min_taps=config.tap_tempo_min_taps,
            quantize_step=TAP_TEMPO_BPM_QUANTIZE_STEP,
        )

    def bind_datapoint_sink(self, sink: ClockDatapointSink | None) -> None:
        self._datapoint_sink = sink

    def register_beat_pulse_listener(self, listener: BeatPulseListener) -> None:
        if listener not in self._beat_pulse_listeners:
            self._beat_pulse_listeners.append(listener)

    def unregister_beat_pulse_listener(self, listener: BeatPulseListener) -> None:
        with contextlib.suppress(ValueError):
            self._beat_pulse_listeners.remove(listener)

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
        if self._bpm_notify_task is not None:
            self._bpm_notify_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._bpm_notify_task
            self._bpm_notify_task = None
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
            if self._datapoint_sink is not None:
                await self._datapoint_sink.publish_outputs()
            else:
                await self._publish_state()
                await self._publish_parameters()

    async def handle_command(self, event: MasterClockCommandEvent) -> None:
        if event.command == "set_bpm":
            await self.set_bpm(float(event.value), source=event.source)
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
        elif event.command == "start_stop":
            if self.running:
                await self.stop_transport()
            else:
                await self.start_transport(reset_position=True)
        elif event.command == "toggle_click":
            await self.toggle_click_enabled()
        elif event.command == "tap_tempo":
            await self.register_tap_tempo()

    async def handle_osc_message(self, event: OscMessageEvent) -> None:
        command = self.remote.command_from_osc(event)
        if command is not None:
            await self.handle_command(command)

    async def handle_midi_message(self, event: MidiMessageEvent) -> None:
        command = self.remote.command_from_midi(event)
        if command is not None:
            await self.handle_command(command)

    async def set_bpm(self, bpm: float, *, source: str | None = None) -> None:
        if not self.config.bpm_min <= bpm <= self.config.bpm_max:
            clamped = min(max(bpm, self.config.bpm_min), self.config.bpm_max)
            if source:
                LOGGER.warning(
                    "bpm %.3f out of range [%.1f, %.1f] from %s; clamping to %.3f",
                    bpm,
                    self.config.bpm_min,
                    self.config.bpm_max,
                    source,
                    clamped,
                )
            else:
                LOGGER.warning(
                    "bpm %.3f out of range [%.1f, %.1f]; clamping to %.3f",
                    bpm,
                    self.config.bpm_min,
                    self.config.bpm_max,
                    clamped,
                )
            bpm = clamped
        if abs(self.bpm - bpm) <= 1e-6:
            return
        self.bpm = bpm
        self.config = replace(self.config, bpm=bpm)
        self.remote = MasterClockRemote(self.config)
        self._schedule_bpm_notify()

    def _schedule_bpm_notify(self) -> None:
        if self._bpm_notify_task is not None and not self._bpm_notify_task.done():
            return
        self._bpm_notify_task = asyncio.create_task(
            self._emit_bpm_notifications(),
            name="master-clock-bpm-notify",
        )

    async def _emit_bpm_notifications(self) -> None:
        try:
            await asyncio.sleep(0)
            published_bpm = self.bpm
            await self.bus.publish(
                BpmChangedEvent(source="master_clock", bpm=published_bpm)
            )
            await self._publish_state()
            await self._publish_parameters()
            if self._datapoint_sink is not None:
                await self._datapoint_sink.publish_outputs()
            if abs(self.bpm - published_bpm) > 1e-6:
                self._schedule_bpm_notify()
        except asyncio.CancelledError:
            raise
        finally:
            if self._bpm_notify_task is asyncio.current_task():
                self._bpm_notify_task = None

    async def flush_bpm_notifications(self) -> None:
        task = self._bpm_notify_task
        if task is not None:
            await task

    async def set_click_enabled(self, enabled: bool) -> None:
        if self.config.click_enabled == enabled:
            return
        self.config = replace(self.config, click_enabled=enabled)
        if enabled:
            await self._prepare_click_audio()
        else:
            await self._release_click_audio()
        await self._publish_state()

    async def toggle_click_enabled(self) -> None:
        await self.set_click_enabled(not self.config.click_enabled)

    async def set_click_interval(self, interval: str) -> None:
        if interval not in CLICK_INTERVAL_TICKS:
            raise ValueError(
                "click interval must be one of: "
                + ", ".join(CLICK_INTERVALS)
            )
        self.click_interval = interval
        await self._publish_state()

    async def start_transport(self, reset_position: bool) -> None:
        was_running = self.running
        if reset_position and not was_running:
            self.position_ticks = 0
        self.running = True
        if self.config.send_transport and not was_running:
            await self._publish_midi_status(MIDI_START)
        await self._prepare_click_audio()
        self._asyncio_loop = asyncio.get_running_loop()
        self._ensure_transport_thread()
        await self._publish_state()

    async def continue_transport(self) -> None:
        self.running = True
        if self.config.send_transport:
            await self._publish_midi_status(MIDI_CONTINUE)
        await self._prepare_click_audio()
        self._asyncio_loop = asyncio.get_running_loop()
        self._ensure_transport_thread()
        await self._publish_state()

    async def stop_transport(self, send_transport: bool = True) -> None:
        self.running = False
        self._transport_stop_event.set()
        await self._join_transport_thread()
        await self._release_click_audio()
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

    def _ensure_transport_thread(self) -> None:
        if self._transport_thread is not None and self._transport_thread.is_alive():
            return
        self._transport_stop_event.clear()
        self._transport_thread = threading.Thread(
            target=self._transport_thread_main,
            name="midijuggler-master-clock",
            daemon=True,
        )
        self._transport_thread.start()

    async def _join_transport_thread(self) -> None:
        thread = self._transport_thread
        if thread is None:
            return
        await asyncio.to_thread(thread.join, 2.0)
        self._transport_thread = None

    async def _halt_transport_thread(self) -> None:
        self._transport_stop_event.set()
        await self._join_transport_thread()

    def _transport_thread_main(self) -> None:
        _try_set_realtime_priority()
        next_tick_at = time.monotonic()
        while self.running and not self._transport_stop_event.is_set():
            interval = self._seconds_per_tick()
            next_tick_at += interval
            delay = next_tick_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -interval * 8:
                next_tick_at = time.monotonic() + interval
            self._emit_frame_from_transport_thread()

    def _emit_frame_from_transport_thread(self) -> None:
        if self._is_click_tick(self.position_ticks):
            if self.config.click_enabled:
                self._trigger_click()
            self._trigger_beat_pulse(self.position_ticks)
        self._submit_coroutine(self._publish_midi_status(MIDI_TIMING_CLOCK))
        self.position_ticks += 1

    def _trigger_beat_pulse(self, position_ticks: int) -> None:
        """Emit beat outputs from the transport thread at the same instant as audio click."""

        for listener in self._beat_pulse_listeners:
            try:
                listener()
            except Exception:
                LOGGER.exception("beat pulse listener failed")
        sink = self._datapoint_sink
        if sink is not None:
            trigger = getattr(sink, "trigger_beat_pulse", None)
            if callable(trigger):
                trigger()
            else:
                self._submit_coroutine(sink.publish_beat())
        self._submit_coroutine(self._publish_click_event(position_ticks))

    def _submit_coroutine(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        loop = self._asyncio_loop
        if loop is None or loop.is_closed():
            coroutine.close()
            return
        if not self.running:
            coroutine.close()
            return
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        future.add_done_callback(self._log_submitted_coroutine_result)

    @staticmethod
    def _log_submitted_coroutine_result(future: asyncio.Future[Any]) -> None:
        with contextlib.suppress(Exception):
            future.result()

    async def _emit_frame(self) -> None:
        if self._is_click_tick(self.position_ticks):
            if self.config.click_enabled:
                self._trigger_click()
            for listener in self._beat_pulse_listeners:
                try:
                    listener()
                except Exception:
                    LOGGER.exception("beat pulse listener failed")
            if self._datapoint_sink is not None:
                await self._datapoint_sink.publish_beat()
            await self._publish_click_event(self.position_ticks)
        await self._publish_midi_status(MIDI_TIMING_CLOCK)
        self.position_ticks += 1

    async def _publish_click_event(self, position_ticks: int) -> None:
        await self.bus.publish(
            ClickEvent(
                source="master_clock",
                interval=self.click_interval,
                position_ticks=position_ticks,
            )
        )

    async def _replace_click_player(self, config: MasterClockConfig) -> None:
        previous = self.click_player
        self.click_player = self._build_click_player(config)
        if previous is not None:
            await previous.close()

    def _build_click_player(self, config: MasterClockConfig) -> ClickPlayer:
        if self.click_audio_device is not None:
            playback_device = self.click_audio_device
        else:
            playback_device, _ = master_clock_playback_target(config.click_audio_device)
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
        configured = config.click_audio_device or playback_device
        if playback_device == MASTER_CLOCK_PCM_NAME:
            return True
        if is_wing_routing_pcm(playback_device) or is_wing_routing_pcm(configured):
            return True
        if not configured:
            return False
        return alsa_mode_for_device(configured) == "dmix"

    def _trigger_click(self) -> None:
        trigger = getattr(self.click_player, "trigger", None)
        if callable(trigger):
            trigger()
            return
        task = asyncio.create_task(self.click_player.play(), name="click-trigger")
        self._click_tasks.add(task)
        task.add_done_callback(self._click_tasks.discard)

    async def _prepare_click_audio(self) -> None:
        if not self.config.click_enabled:
            return
        prepare = getattr(self.click_player, "prepare", None)
        if callable(prepare):
            await prepare()

    async def _release_click_audio(self) -> None:
        release = getattr(self.click_player, "release", None)
        if callable(release):
            await release()

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
                click_enabled=self.config.click_enabled,
            )
        )

    async def _publish_parameters(self) -> None:
        for control, value in self.parameters.as_controls().items():
            if control not in CLOCK_BUS_CONTROL_PUBLISH:
                continue
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
    clamped = max(0, min(int(value), 127))
    index = (clamped * len(CLICK_INTERVALS)) // 128
    if index >= len(CLICK_INTERVALS):
        index = len(CLICK_INTERVALS) - 1
    return CLICK_INTERVALS[index]
