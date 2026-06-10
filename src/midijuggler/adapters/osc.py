"""OSC adapter for UDP input and output."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from midijuggler.adapters.base import Adapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import (
    AdapterStatusEvent,
    ControlEvent,
    MappedEvent,
    OscMessageEvent,
)
from midijuggler.osc.protocol import decode_messages, encode_message

LOGGER = logging.getLogger(__name__)


class OscAdapter(Adapter):
    protocol = "OSC"

    def __init__(self, name: str, config: AdapterConfig, bus: EventBus) -> None:
        super().__init__(name, config, bus)
        self._listen_host = str(config.options.get("listen_host", "0.0.0.0")).strip()
        self._listen_port = int(config.options.get("listen_port", 9000))
        self._remote_host = str(config.options.get("remote_host", "")).strip()
        self._remote_port = int(config.options.get("remote_port", 0))
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _OscDatagramProtocol | None = None

    async def start(self) -> None:
        self._listen_host = str(self.config.options.get("listen_host", "0.0.0.0")).strip()
        self._listen_port = int(self.config.options.get("listen_port", 9000))
        self._remote_host = str(self.config.options.get("remote_host", "")).strip()
        self._remote_port = int(self.config.options.get("remote_port", 0))

        loop = asyncio.get_running_loop()
        bind_port = self._listen_port if self._listen_port > 0 else 0
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _OscDatagramProtocol(self),
            local_addr=(self._listen_host, bind_port),
        )

        detail_parts = []
        if self._listen_port > 0:
            detail_parts.append(f"listening on {self._listen_host}:{self._listen_port}")
        elif bind_port == 0 and self._transport is not None:
            detail_parts.append("bound to ephemeral UDP port for output")
        if self._remote_host and self._remote_port > 0:
            detail_parts.append(f"sending to {self._remote_host}:{self._remote_port}")
        detail = "OSC adapter active"
        if detail_parts:
            detail = "OSC adapter " + ", ".join(detail_parts)

        self.running = True
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="started",
                detail=detail,
            )
        )

    async def reload(self, config: AdapterConfig) -> None:
        self.config = config
        if not self.running:
            return
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        self.running = False
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            self._protocol = None

        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail="OSC adapter stopped",
            )
        )

    async def handle_datagram(self, data: bytes) -> None:
        try:
            messages = decode_messages(data)
        except ValueError:
            LOGGER.debug("OSC adapter %s ignored invalid datagram", self.name)
            return

        for address, arguments in messages:
            await self.bus.publish(
                OscMessageEvent(
                    source=self.name,
                    address=address,
                    arguments=arguments,
                    direction="input",
                )
            )
            numeric_value = _first_numeric_argument(arguments)
            if numeric_value is not None:
                await self.bus.publish(
                    ControlEvent(
                        source=self.name,
                        control=address,
                        value=numeric_value,
                    )
                )

    async def send(self, event: MappedEvent) -> None:
        address = _target_address(self.name, event.target)
        if address is None:
            await super().send(event)
            return
        if not self._remote_host or self._remote_port <= 0:
            LOGGER.warning(
                "OSC adapter %s has no remote_host/remote_port configured for %s",
                self.name,
                event.target,
            )
            return
        if self._transport is None:
            LOGGER.warning("OSC adapter %s is not running and cannot send", self.name)
            return

        payload = encode_message(address, [float(event.value)])
        self._transport.sendto(payload, (self._remote_host, self._remote_port))
        await self.bus.publish(
            OscMessageEvent(
                source=self.name,
                address=address,
                arguments=(float(event.value),),
                target=event.target,
                direction="output",
            )
        )


class _OscDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, adapter: OscAdapter) -> None:
        self._adapter = adapter

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.create_task(self._adapter.handle_datagram(data))


def _target_address(adapter_name: str, target: str) -> str | None:
    prefix, separator, remainder = target.partition(":")
    if not separator or prefix != adapter_name or not remainder.startswith("/"):
        return None
    return remainder


def _first_numeric_argument(arguments: tuple[Any, ...]) -> float | None:
    for argument in arguments:
        if isinstance(argument, bool):
            return 1.0 if argument else 0.0
        if isinstance(argument, (int, float)):
            return float(argument)
    return None
