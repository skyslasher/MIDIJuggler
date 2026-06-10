"""MIDI master clock, remote control and optional audio click."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

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

LOGGER = logging.getLogger(__name__)

MIDI_TIMING_CLOCK = 0xF8
MIDI_START = 0xFA
MIDI_CONTINUE = 0xFB
MIDI_STOP = 0xFC

CLICK_INTERVAL_TICKS = {
    "eighth": MIDI_CLOCK_TICKS_PER_QUARTER // 2,
    "quarter": MIDI_CLOCK_TICKS_PER_QUARTER,
    "half": MIDI_CLOCK_TICKS_PER_QUARTER * 2,
    "whole": MIDI_CLOCK_TICKS_PER_QUARTER * 4,
}


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


class ClickPlayer:
    """Play an audio click WAV through ALSA's aplay command."""

    def __init__(
        self,
        wav_path: str,
        command: str = "aplay",
        audio_device: str = "",
    ) -> None:
        self.wav_path = wav_path
        self.command = command
        self.audio_device = audio_device

    async def play(self) -> None:
        if not self.wav_path:
            return
        if not Path(self.wav_path).is_file():
            LOGGER.warning("click WAV does not exist: %s", self.wav_path)
            return

        command = [self.command, "-q"]
        if self.audio_device:
            command.extend(["-D", self.audio_device])
        command.append(self.wav_path)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            LOGGER.exception("failed to start click playback command")
            return

        asyncio.create_task(self._wait_for_process(process), name="click-playback")

    async def _wait_for_process(self, process: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(Exception):
            await process.wait()


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
    ) -> None:
        self.config = config
        self.bus = bus
        self.bpm = config.bpm
        self.click_interval = config.click_interval
        self.running = False
        self.position_ticks = 0
        self.remote = MasterClockRemote(config)
        self.click_player = click_player or ClickPlayer(
            config.click_wav,
            command=config.click_command,
            audio_device=config.click_audio_device,
        )
        self._task: asyncio.Task[None] | None = None

    @property
    def parameters(self) -> MasterClockParameters:
        return bpm_to_parameters(self.bpm)

    async def start(self) -> None:
        await self._publish_state()
        await self._publish_parameters()
        if self.config.enabled and self.config.auto_start:
            await self.start_transport(reset_position=True)

    async def stop(self) -> None:
        await self.stop_transport(send_transport=False)

    async def configure(self, config: MasterClockConfig) -> None:
        """Apply a new master-clock configuration at runtime."""

        was_running = self.running
        if was_running and not config.enabled:
            await self.stop_transport(send_transport=config.send_transport)

        self.config = config
        self.remote = MasterClockRemote(config)
        self.click_player = ClickPlayer(
            config.click_wav,
            command=config.click_command,
            audio_device=config.click_audio_device,
        )
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
        if reset_position:
            self.position_ticks = 0
        self.running = True
        if self.config.send_transport:
            await self._publish_midi_status(MIDI_START)
        self._ensure_task()
        await self._publish_state()

    async def continue_transport(self) -> None:
        self.running = True
        if self.config.send_transport:
            await self._publish_midi_status(MIDI_CONTINUE)
        self._ensure_task()
        await self._publish_state()

    async def stop_transport(self, send_transport: bool = True) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if send_transport and self.config.send_transport:
            await self._publish_midi_status(MIDI_STOP)
        await self._publish_state()

    async def emit_tick(self) -> None:
        """Emit one MIDI clock tick. Exposed for tests and deterministic stepping."""

        if self.config.click_enabled and self._is_click_tick():
            await self.click_player.play()
            await self.bus.publish(
                ClickEvent(
                    source="master_clock",
                    interval=self.click_interval,
                    position_ticks=self.position_ticks,
                )
            )
        await self._publish_midi_status(MIDI_TIMING_CLOCK)
        self.position_ticks += 1

    def _ensure_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="master-clock")

    async def _run(self) -> None:
        while self.running:
            started = asyncio.get_running_loop().time()
            await self.emit_tick()
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.0, self._seconds_per_tick() - elapsed))

    def _seconds_per_tick(self) -> float:
        return 60.0 / (self.bpm * MIDI_CLOCK_TICKS_PER_QUARTER)

    def _is_click_tick(self) -> bool:
        return self.position_ticks % CLICK_INTERVAL_TICKS[self.click_interval] == 0

    async def _publish_midi_status(self, status: int) -> None:
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
