"""RTP-MIDI adapter with mDNS session hosting and discovery."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from midijuggler.adapters.base import Adapter
from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, MappedEvent, MidiMessageEvent
from midijuggler.midi.output import send_midi_message_to_port
from midijuggler.device.lookup import device_id_for_adapter
from midijuggler.device.registry import DeviceRegistry
from midijuggler.midi.target_encode import encode_mapped_midi_target
from midijuggler.system_info import resolve_midi_output_port_address

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
        app_config: AppConfig | None = None,
    ) -> None:
        super().__init__(name, config, bus)
        self.manager = manager
        self._app_config = app_config

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
        if role == "listen":
            return (
                f"RTP-MIDI listen-only session {session_name or 'unnamed'} on UDP {port}"
            )
        return f"RTP-MIDI host session {session_name or 'unnamed'} on UDP {port}"

    def _resolve_output_address(self) -> str | None:
        output_port = str(self.config.options.get("output_port", "")).strip()
        if not output_port:
            return None
        return resolve_midi_output_port_address(output_port)

    async def send_midi_message(self, event: MidiMessageEvent) -> None:
        output_address = self._resolve_output_address()
        if output_address is None:
            LOGGER.warning(
                "RTP-MIDI adapter %s has no output_port configured; dropped %s",
                self.name,
                event.as_dict(),
            )
            return

        await self._emit_midi_output(output_address, event)

    async def send(self, event: MappedEvent) -> None:
        module, separator, point = event.target.partition(":")
        if not separator or module != self.name:
            await super().send(event)
            return
        if self._app_config is None:
            LOGGER.warning(
                "RTP-MIDI adapter %s cannot send mapped event without app config: %s",
                self.name,
                event.target,
            )
            return
        try:
            device_id = device_id_for_adapter(self._app_config, self.name)
            registry = DeviceRegistry.from_config(self._app_config)
            status, data = encode_mapped_midi_target(
                self._app_config,
                registry,
                device_id,
                point,
                event.value,
            )
        except ValueError:
            LOGGER.warning(
                "RTP-MIDI adapter %s cannot encode mapped target %s",
                self.name,
                event.target,
            )
            return
        await self.send_midi_message(
            MidiMessageEvent(
                source=self.name,
                status=status,
                data=data,
                target=event.target,
                direction="output",
            )
        )

    async def send_test_message(self, status: int, data: tuple[int, ...]) -> None:
        output_address = self._resolve_output_address()
        if output_address is None:
            raise OSError(
                f"RTP-MIDI adapter {self.name} has no output_port configured for sending"
            )

        await self._emit_midi_output(
            output_address,
            MidiMessageEvent(
                source=self.name,
                status=status,
                data=data,
                direction="output",
            ),
        )

    async def _emit_midi_output(
        self,
        output_address: str,
        event: MidiMessageEvent,
    ) -> None:
        await send_midi_message_to_port(output_address, event.status, event.data)
        await self.bus.publish(
            MidiMessageEvent(
                source=self.name,
                status=event.status,
                data=event.data,
                target=event.target,
                direction="output",
            )
        )
