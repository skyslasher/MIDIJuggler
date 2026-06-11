"""OSC adapter for UDP input and output."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import logging
import socket
import time
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
from midijuggler.osc.desk_protocol import (
    DeskProtocol,
    apply_desk_options,
    desk_protocol_for_library,
    sync_query_addresses,
)
from midijuggler.osc.protocol import decode_messages, encode_message

LOGGER = logging.getLogger(__name__)

PROXY_CLIENT_TIMEOUT_SECONDS = 60.0


class OscAdapter(Adapter):
    protocol = "OSC"

    def __init__(self, name: str, config: AdapterConfig, bus: EventBus) -> None:
        super().__init__(name, config, bus)
        self._apply_options(config.options)
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _OscDatagramProtocol | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._proxy_clients: dict[tuple[str, int], float] = {}

    def _apply_options(self, options: dict[str, Any]) -> None:
        normalized = apply_desk_options(dict(options))
        self._listen_host = str(normalized.get("listen_host", "0.0.0.0")).strip()
        self._listen_port = int(normalized.get("listen_port", 9000))
        self._remote_host = str(normalized.get("remote_host", "")).strip()
        self._remote_port = int(normalized.get("remote_port", 0))
        self._desk_protocol = desk_protocol_for_library(
            str(normalized.get("osc_library", "")).strip()
        )
        self._desk_sync_on_connect = bool(normalized.get("desk_sync_on_connect", False))
        self._desk_proxy_mode = bool(normalized.get("desk_proxy_mode", False))

    @property
    def desk_proxy_client_count(self) -> int:
        self._prune_proxy_clients()
        return len(self._proxy_clients)

    def _bind_address(self) -> tuple[str, int]:
        bind_port = self._listen_port if self._listen_port > 0 else 0
        return (self._listen_host, bind_port)

    async def start(self) -> None:
        self._apply_options(self.config.options)

        loop = asyncio.get_running_loop()
        bind_host, bind_port = self._bind_address()
        try:
            sock = _create_datagram_socket(bind_host, bind_port)
            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: _OscDatagramProtocol(self),
                sock=sock,
            )
        except OSError as exc:
            if exc.errno in {errno.EADDRINUSE, errno.EACCES, errno.EADDRNOTAVAIL}:
                raise OSError(
                    exc.errno,
                    f"cannot bind OSC adapter {self.name} to {bind_host}:{bind_port}: {exc}",
                ) from exc
            raise

        detail_parts = []
        if self._listen_port > 0:
            detail_parts.append(f"listening on {self._listen_host}:{self._listen_port}")
        elif bind_port == 0 and self._transport is not None:
            detail_parts.append("bound to ephemeral UDP port for output")
        if self._remote_host and self._remote_port > 0:
            detail_parts.append(f"sending to {self._remote_host}:{self._remote_port}")
        if self._desk_protocol is not None:
            detail_parts.append(f"desk mode {self._desk_protocol.protocol_id}")
        if self._desk_proxy_mode:
            detail_parts.append("proxy mode active")
        detail = "OSC adapter active"
        if detail_parts:
            detail = "OSC adapter " + ", ".join(detail_parts)

        self.running = True
        await self._start_desk_session()

        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="started",
                detail=detail,
            )
        )

    async def reload(self, config: AdapterConfig) -> None:
        previous_bind = self._bind_address() if self.running else None
        self.config = config
        self._apply_options(config.options)
        if not self.running:
            return
        if previous_bind == self._bind_address():
            await self._restart_desk_session()
            return
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        self.running = False
        await self._stop_desk_session()

        self._proxy_clients.clear()
        if self._transport is not None:
            transport = self._transport
            transport.close()
            with contextlib.suppress(Exception):
                await transport.wait_closed()
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

    async def handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._desk_proxy_mode:
            await self._handle_proxy_datagram(data, addr)
            return
        await self._handle_input_messages(data)

    async def _handle_proxy_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        host, _port = addr
        if self._is_desk_addr(host):
            await self._handle_input_messages(data)
            await self._forward_to_proxy_clients(data, exclude=addr)
            return

        self._register_proxy_client(addr)
        if self._remote_host and self._remote_port > 0 and self._transport is not None:
            self._transport.sendto(data, (self._remote_host, self._remote_port))

    async def _handle_input_messages(self, data: bytes) -> None:
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

    async def _start_desk_session(self) -> None:
        if self._desk_protocol is None or not self._remote_host or self._remote_port <= 0:
            return
        await self._send_desk_keepalive()
        if self._desk_sync_on_connect:
            await self._desk_sync()
        self._keepalive_task = asyncio.create_task(
            self._keepalive_loop(),
            name=f"osc-keepalive-{self.name}",
        )

    async def _stop_desk_session(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._keepalive_task
            self._keepalive_task = None

    async def _restart_desk_session(self) -> None:
        await self._stop_desk_session()
        await self._start_desk_session()

    async def _keepalive_loop(self) -> None:
        interval = self._desk_protocol.keepalive_interval if self._desk_protocol else 9.0
        try:
            while self.running:
                await asyncio.sleep(interval)
                if not self.running:
                    break
                await self._send_desk_keepalive()
        except asyncio.CancelledError:
            raise

    async def _send_desk_keepalive(self) -> None:
        if self._desk_protocol is None or not self._remote_host or self._remote_port <= 0:
            return
        if self._transport is None:
            return
        payload = encode_message(self._desk_protocol.keepalive_address, [])
        self._transport.sendto(payload, (self._remote_host, self._remote_port))

    async def _desk_sync(self) -> None:
        if self._desk_protocol is None or not self._remote_host or self._remote_port <= 0:
            return
        if self._transport is None:
            return

        library_id = str(self.config.options.get("osc_library", "")).strip()
        if not library_id:
            return

        for address in sync_query_addresses(library_id):
            payload = encode_message(address, [])
            self._transport.sendto(payload, (self._remote_host, self._remote_port))
            await asyncio.sleep(0.001)

    async def _forward_to_proxy_clients(
        self,
        data: bytes,
        *,
        exclude: tuple[str, int] | None = None,
    ) -> None:
        if self._transport is None:
            return
        self._prune_proxy_clients()
        for client_addr in self._proxy_clients:
            if exclude is not None and client_addr == exclude:
                continue
            self._transport.sendto(data, client_addr)

    def _register_proxy_client(self, addr: tuple[str, int]) -> None:
        self._proxy_clients[addr] = time.monotonic()

    def _prune_proxy_clients(self) -> None:
        cutoff = time.monotonic() - PROXY_CLIENT_TIMEOUT_SECONDS
        expired = [addr for addr, seen_at in self._proxy_clients.items() if seen_at < cutoff]
        for addr in expired:
            self._proxy_clients.pop(addr, None)

    def _is_desk_addr(self, host: str) -> bool:
        if not self._remote_host:
            return False
        return host == self._remote_host


class _OscDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, adapter: OscAdapter) -> None:
        self._adapter = adapter

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.create_task(self._adapter.handle_datagram(data, addr))


def _create_datagram_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind((host, port))
    sock.setblocking(False)
    return sock


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
