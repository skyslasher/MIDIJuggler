"""RTP-MIDI adapter with mDNS session hosting and discovery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from midijuggler.adapters.base import Adapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent

if TYPE_CHECKING:
    from midijuggler.rtp_midi.manager import RtpMidiManager

LOGGER = logging.getLogger(__name__)


class RtpMidiAdapter(Adapter):
    protocol = "RTP-MIDI"

    def __init__(
        self,
        name: str,
        config: AdapterConfig,
        bus: EventBus,
        manager: RtpMidiManager | None = None,
    ) -> None:
        super().__init__(name, config, bus)
        self.manager = manager

    async def start(self) -> None:
        self.running = True
        if self.manager is not None:
            await self.manager.apply_instance(self.name, self.config)
        detail = self._status_detail()
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="started",
                detail=detail,
            )
        )

    async def stop(self) -> None:
        if self.manager is not None:
            await self.manager.remove_instance(self.name)
        self.running = False
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail="RTP-MIDI adapter stopped",
            )
        )

    def _status_detail(self) -> str:
        role = str(self.config.options.get("role", "host"))
        if role == "join":
            target = str(self.config.options.get("join_target", "")).strip()
            return f"RTP-MIDI join mode targeting {target or 'no session selected'}"
        session_name = str(self.config.options.get("session_name", "")).strip()
        port = int(self.config.options.get("port", 5004))
        return f"RTP-MIDI host session {session_name or 'unnamed'} on UDP {port}"
