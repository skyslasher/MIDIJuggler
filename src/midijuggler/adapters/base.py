"""Base classes for hardware and protocol adapters."""

from __future__ import annotations

import logging
from abc import ABC

from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, MappedEvent, MidiMessageEvent

LOGGER = logging.getLogger(__name__)


class Adapter(ABC):
    """Lifecycle boundary for an input/output adapter."""

    protocol = "adapter"

    def __init__(self, name: str, config: AdapterConfig, bus: EventBus) -> None:
        self.name = name
        self.config = config
        self.bus = bus
        self.running = False

    async def start(self) -> None:
        self.running = True
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="started",
                detail=f"{self.protocol} adapter stub active",
            )
        )

    async def stop(self) -> None:
        self.running = False
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail=f"{self.protocol} adapter stopped",
            )
        )

    async def send(self, event: MappedEvent) -> None:
        """Send a mapped event to the adapter target.

        Concrete adapters will translate the normalized event into OSC, MIDI,
        RTP-MIDI or GPIO-specific output operations.
        """

        LOGGER.info("%s stub received mapped event: %s", self.name, event.as_dict())

    async def send_midi_message(self, event: MidiMessageEvent) -> None:
        """Send a MIDI message to a MIDI-capable adapter."""

        LOGGER.info("%s stub received MIDI message: %s", self.name, event.as_dict())
