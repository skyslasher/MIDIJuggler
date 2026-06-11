"""Service orchestration for MIDIJuggler."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import replace
from pathlib import Path

from midijuggler.adapters import build_adapters
from midijuggler.adapters.base import Adapter
from midijuggler.adapters.gpio import GpioAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.alsa import (
    MASTER_CLOCK_PCM_NAME,
    alsa_config_path_for_config,
    write_master_clock_pcm_config,
)
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AppConfig, load_config
from midijuggler.eventbus import EventBus
from midijuggler.events import (
    BpmChangedEvent,
    ControlEvent,
    MasterClockCommandEvent,
    MidiClockEvent,
    MidiMessageEvent,
    MappedEvent,
    OscMessageEvent,
)
from midijuggler.master_clock import MIDI_TIMING_CLOCK, MasterClock
from midijuggler.mapping import MappingEngine
from midijuggler.rtp_midi import RtpMidiManager
from midijuggler.web.server import WebInterface, run_web_server, stop_web_server

LOGGER = logging.getLogger(__name__)


class MIDIJugglerService:
    """Wire core services, adapters and web UI together."""

    def __init__(self, config: AppConfig, config_path: str | Path | None = None) -> None:
        self.config = config
        self.config_path = Path(config_path) if config_path is not None else None
        self.alsa_config_path = alsa_config_path_for_config(self.config_path)
        self.bus = EventBus()
        self.clock = ClockBpmTracker()
        self.mapping = MappingEngine(config.mappings)
        self.rtp_midi_manager = RtpMidiManager()
        self.adapters = build_adapters(
            config.adapters,
            self.bus,
            rtp_midi_manager=self.rtp_midi_manager,
        )
        self._write_master_clock_alsa_config(self.config.master_clock.click_audio_device)
        self.master_clock = MasterClock(
            self._master_clock_config(),
            self.bus,
            click_audio_device=MASTER_CLOCK_PCM_NAME,
            alsa_config_path=self.alsa_config_path,
        )
        self.web = WebInterface(
            config,
            self.bus,
            self.clock,
            self.master_clock,
            gpio_adapter=self._gpio_adapter(),
            midi_adapters=self._midi_adapters(),
            rtp_midi_adapters=self._rtp_midi_adapters(),
            osc_adapters=self._osc_adapters(),
            mapping_engine=self.mapping,
            rtp_midi_manager=self.rtp_midi_manager,
            runtime_adapters=self.adapters,
            config_path=self.config_path,
            alsa_config_path=self.alsa_config_path,
        )
        self._runner = None

        self.bus.subscribe(MidiClockEvent, self._track_clock)
        self.bus.subscribe(ControlEvent, self._map_control)
        self.bus.subscribe(MappedEvent, self._route_mapped_event)
        self.bus.subscribe(MidiMessageEvent, self._handle_midi_message)
        self.bus.subscribe(OscMessageEvent, self._handle_osc_message)
        self.bus.subscribe(MasterClockCommandEvent, self._handle_master_clock_command)

    async def start(self) -> None:
        LOGGER.info("starting MIDIJuggler")
        await self.rtp_midi_manager.start()
        LOGGER.info("RTP-MIDI status: %s", self.rtp_midi_manager.status_summary())
        for adapter in self.adapters:
            await adapter.start()
        await self.master_clock.start()
        self._runner = await run_web_server(self.web)
        LOGGER.info(
            "web interface listening on http://%s:%s",
            self.config.web.host,
            self.config.web.port,
        )

    async def stop(self) -> None:
        LOGGER.info("stopping MIDIJuggler")
        if self._runner is not None:
            await stop_web_server(self._runner)
            self._runner = None
        await self.master_clock.stop()
        for adapter in reversed(self.adapters):
            await adapter.stop()
        await self.rtp_midi_manager.stop()

    async def run_forever(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    async def _track_clock(self, event: MidiClockEvent) -> None:
        bpm = self.clock.tick(event.timestamp)
        if bpm is not None:
            await self.bus.publish(BpmChangedEvent(source="clock", bpm=bpm))

    async def _map_control(self, event: ControlEvent) -> None:
        await self.bus.publish_many(self.mapping.map_event(event))

    async def _route_mapped_event(self, event: MappedEvent) -> None:
        adapter = self._adapter_for_target(event.target)
        if adapter is None:
            LOGGER.warning("no enabled adapter for target %s", event.target)
            return
        await adapter.send(event)

    async def _handle_midi_message(self, event: MidiMessageEvent) -> None:
        if event.direction == "input" and self.config.master_clock.enabled:
            if event.source in self._allowed_midi_input_sources():
                await self.master_clock.handle_midi_message(event)
            return

        if event.direction != "output":
            return
        adapter = self._adapter_for_target(event.target)
        if adapter is None:
            if event.status == MIDI_TIMING_CLOCK:
                return
            LOGGER.warning("no enabled adapter for MIDI target %s", event.target)
            return
        await adapter.send_midi_message(event)

    async def _handle_osc_message(self, event: OscMessageEvent) -> None:
        if event.direction == "input" and self.config.master_clock.enabled:
            if event.source in self._allowed_osc_input_sources():
                await self.master_clock.handle_osc_message(event)

    async def _handle_master_clock_command(self, event: MasterClockCommandEvent) -> None:
        if self.config.master_clock.enabled:
            await self.master_clock.handle_command(event)

    def _adapter_for_target(self, target: str) -> Adapter | None:
        adapter_name = target.split(":", 1)[0]
        return next((adapter for adapter in self.adapters if adapter.name == adapter_name), None)

    def _enabled_adapter_names(self, kinds: set[str]) -> set[str]:
        return {
            adapter.name
            for adapter in self.adapters
            if adapter.config.enabled and (adapter.config.kind or adapter.name) in kinds
        }

    def _allowed_midi_input_sources(self) -> set[str]:
        enabled = self._enabled_adapter_names({"midi", "rtp_midi"})
        configured = self.config.master_clock.midi_input_targets
        if configured is None:
            return enabled
        return enabled & set(configured)

    def _allowed_osc_input_sources(self) -> set[str]:
        enabled = self._enabled_adapter_names({"osc"})
        configured = self.config.master_clock.osc_input_targets
        if configured is None:
            return enabled
        return enabled & set(configured)

    def _gpio_adapter(self) -> GpioAdapter | None:
        return next(
            (adapter for adapter in self.adapters if isinstance(adapter, GpioAdapter)),
            None,
        )

    def _midi_adapters(self) -> dict[str, MidiAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, MidiAdapter)
        }

    def _osc_adapters(self) -> dict[str, OscAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, OscAdapter)
        }

    def _rtp_midi_adapters(self) -> dict[str, RtpMidiAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, RtpMidiAdapter)
        }

    def _master_clock_config(self):
        enabled_midi_targets = {
            adapter.name
            for adapter in self.adapters
            if adapter.config.enabled and adapter.config.kind in {"midi", "rtp_midi"}
        }
        output_targets = [
            target
            for target in self.config.master_clock.output_targets
            if target in enabled_midi_targets
        ]
        dropped_targets = set(self.config.master_clock.output_targets) - set(output_targets)
        if dropped_targets:
            LOGGER.warning(
                "ignoring disabled MIDI clock output targets: %s",
                ", ".join(sorted(dropped_targets)),
            )
        return replace(self.config.master_clock, output_targets=output_targets)

    def _write_master_clock_alsa_config(self, audio_device: str) -> None:
        if self.alsa_config_path is None:
            return
        try:
            write_master_clock_pcm_config(self.alsa_config_path, audio_device)
        except OSError:
            LOGGER.exception(
                "could not write ALSA dmix config for master clock to %s",
                self.alsa_config_path,
            )


async def run_from_config(config_path: str) -> None:
    config = load_config(config_path)
    service = MIDIJugglerService(config, config_path=config_path)
    with contextlib.suppress(asyncio.CancelledError):
        await service.run_forever()
