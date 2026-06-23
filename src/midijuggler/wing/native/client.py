"""Async Wing native TCP client."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from midijuggler.wing.native.decoder import (
    WingDecodeKind,
    WingNodeData,
    WingNodeDef,
    WingStreamDecoder,
)
from midijuggler.wing.native.protocol import (
    AUDIO_ENGINE_CHANNEL,
    WING_NATIVE_PORT,
    encode_keepalive,
    encode_request_node_definition,
    encode_set_float,
    encode_set_int,
)

LOGGER = logging.getLogger(__name__)
KEEPALIVE_INTERVAL_SECONDS = 7.0


@dataclass(frozen=True)
class WingPathBinding:
    path: str
    node_id: int


class WingNativeClient:
    """Manage a Wing native TCP session on the audio-engine channel."""

    def __init__(
        self,
        host: str,
        *,
        port: int = WING_NATIVE_PORT,
        channel: int = AUDIO_ENGINE_CHANNEL,
    ) -> None:
        self.host = host.strip()
        self.port = port
        self.channel = channel
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._decoder = WingStreamDecoder()
        self._path_to_id: dict[str, int] = {}
        self._id_to_path: dict[int, str] = {}
        self._pending_defs: asyncio.Future[list[WingNodeDef]] | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        await self._write(encode_keepalive(self.channel))

    async def close(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def keepalive(self) -> None:
        await self._write(encode_keepalive(self.channel))

    async def resolve_path(self, path: str) -> int:
        normalized = _normalize_path(path)
        cached = self._path_to_id.get(normalized)
        if cached is not None:
            return cached

        parts = [part for part in normalized.strip("/").split("/") if part]
        node_id = 0
        current_path = ""
        for part in parts:
            current_path = f"{current_path}/{part}"
            if current_path in self._path_to_id:
                node_id = self._path_to_id[current_path]
                continue
            children = await self.list_children(node_id)
            match = next((child for child in children if child.name == part), None)
            if match is None:
                raise KeyError(f"Wing path segment {part!r} not found under {current_path!r}")
            node_id = match.node_id
            self._remember_path(current_path, node_id)
        self._remember_path(normalized, node_id)
        return node_id

    async def list_children(self, node_id: int) -> list[WingNodeDef]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            pending: asyncio.Future[list[WingNodeDef]] = loop.create_future()
            self._pending_defs = pending
            await self._write(encode_request_node_definition(node_id, self.channel))
            try:
                return await asyncio.wait_for(pending, timeout=5.0)
            finally:
                self._pending_defs = None

    async def set_float(self, node_id: int, value: float) -> None:
        await self._write(encode_set_float(node_id, value, channel=self.channel))

    async def set_int(self, node_id: int, value: int) -> None:
        await self._write(encode_set_int(node_id, value, channel=self.channel))

    async def read_events(self) -> list[tuple[WingDecodeKind, object]]:
        if self._reader is None:
            return []
        try:
            data = await asyncio.wait_for(self._reader.read(4096), timeout=KEEPALIVE_INTERVAL_SECONDS)
        except TimeoutError:
            return []
        if not data:
            raise ConnectionError("Wing native connection closed")
        return self._decoder.feed(data)

    def remember_binding(self, binding: WingPathBinding) -> None:
        self._remember_path(binding.path, binding.node_id)

    def path_for_node(self, node_id: int) -> str | None:
        return self._id_to_path.get(node_id)

    @property
    def path_cache_size(self) -> int:
        return len(self._path_to_id)

    def handle_events(self, events: list[tuple[WingDecodeKind, object]]) -> list[WingNodeDef | WingNodeData]:
        handled: list[WingNodeDef | WingNodeData] = []
        pending = self._pending_defs
        collected: list[WingNodeDef] = []
        for kind, payload in events:
            if kind == WingDecodeKind.NODE_DEF and isinstance(payload, WingNodeDef):
                collected.append(payload)
                handled.append(payload)
            elif kind == WingDecodeKind.NODE_DATA and isinstance(payload, WingNodeData):
                handled.append(payload)
            elif kind == WingDecodeKind.REQUEST_END and pending is not None and not pending.done():
                pending.set_result(collected)
        return handled

    def _remember_path(self, path: str, node_id: int) -> None:
        normalized = _normalize_path(path)
        self._path_to_id[normalized] = node_id
        self._id_to_path[node_id] = normalized

    async def _write(self, payload: bytes) -> None:
        if self._writer is None:
            raise ConnectionError("Wing native client is not connected")
        self._writer.write(payload)
        await self._writer.drain()


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized
