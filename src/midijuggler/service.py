"""Service orchestration for MIDIJuggler."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from midijuggler.adapters import build_adapters
from midijuggler.adapters.base import Adapter
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
from midijuggler.master_clock import MasterClock
from midijuggler.mapping import MappingEngine
from midijuggler.web.server import WebInterface, run_web_server, stop_web_server

LOGGER = logging.getLogger(__name__)


class MIDIJugglerService:
    """Wire core services, adapters and web UI together."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.bus = EventBus()
        self.clock = ClockBpmTracker()
        self.master_clock = MasterClock(config.master_clock, self.bus)
        self.mapping = MappingEngine(config.mappings)
        self.adapters = build_adapters(config.adapters, self.bus)
        self.web = WebInterface(config, self.bus, self.clock, self.master_clock)
        self._runner = None

        self.bus.subscribe(MidiClockEvent, self._track_clock)
        self.bus.subscribe(ControlEvent, self._map_control)
        self.bus.subscribe(MappedEvent, self._route_mapped_event)
        self.bus.subscribe(MidiMessageEvent, self._handle_midi_message)
        self.bus.subscribe(OscMessageEvent, self._handle_osc_message)
        self.bus.subscribe(MasterClockCommandEvent, self._handle_master_clock_command)

    async def start(self) -> None:
        LOGGER.info("starting MIDIJuggler")
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
            await self.master_clock.handle_midi_message(event)
            return

        if event.direction != "output":
            return
        adapter = self._adapter_for_target(event.target)
        if adapter is None:
            LOGGER.warning("no enabled adapter for MIDI target %s", event.target)
            return
        await adapter.send_midi_message(event)

    async def _handle_osc_message(self, event: OscMessageEvent) -> None:
        if event.direction == "input" and self.config.master_clock.enabled:
            await self.master_clock.handle_osc_message(event)

    async def _handle_master_clock_command(self, event: MasterClockCommandEvent) -> None:
        if self.config.master_clock.enabled:
            await self.master_clock.handle_command(event)

    def _adapter_for_target(self, target: str) -> Adapter | None:
        adapter_name = target.split(":", 1)[0]
        return next((adapter for adapter in self.adapters if adapter.name == adapter_name), None)


async def run_from_config(config_path: str) -> None:
    config = load_config(config_path)
    service = MIDIJugglerService(config)
    with contextlib.suppress(asyncio.CancelledError):
        await service.run_forever()
