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
LIST_CHILDREN_TIMEOUT_SECONDS = 5.0
LIST_CHILDREN_DRAIN_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class WingPathBinding:
    path: str
    node_id: int


@dataclass
class _PendingNodeDefRequest:
    future: asyncio.Future[list[WingNodeDef]]
    request_id: int


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
        self._pending_node_defs: _PendingNodeDefRequest | None = None
        self._node_def_request_seq = 0
        self._discard_node_defs_until_end = False
        self._discard_node_defs_done: asyncio.Future[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        await self.keepalive()

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
            await self._wait_for_stale_node_def_drain()
            self._node_def_request_seq += 1
            request_id = self._node_def_request_seq
            loop = asyncio.get_running_loop()
            pending: asyncio.Future[list[WingNodeDef]] = loop.create_future()
            self._pending_node_defs = _PendingNodeDefRequest(
                future=pending,
                request_id=request_id,
            )
            await self.keepalive()
            await self._write(encode_request_node_definition(node_id))
            try:
                return await asyncio.wait_for(
                    pending,
                    timeout=LIST_CHILDREN_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                LOGGER.warning(
                    "Wing native list_children timed out after %.1fs for node_id=%s",
                    LIST_CHILDREN_TIMEOUT_SECONDS,
                    node_id,
                )
                self._begin_stale_node_def_drain()
                if not pending.done():
                    pending.cancel()
                raise
            finally:
                if (
                    self._pending_node_defs is not None
                    and self._pending_node_defs.request_id == request_id
                ):
                    self._pending_node_defs = None

    async def set_float(self, node_id: int, value: float) -> None:
        await self._write(encode_set_float(node_id, value))

    async def set_int(self, node_id: int, value: int) -> None:
        await self._write(encode_set_int(node_id, value))

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
        if self._discard_node_defs_until_end:
            for kind, payload in events:
                if kind == WingDecodeKind.NODE_DATA and isinstance(payload, WingNodeData):
                    handled.append(payload)
                elif kind == WingDecodeKind.REQUEST_END:
                    self._finish_stale_node_def_drain()
            return handled

        pending_req = self._pending_node_defs
        collected: list[WingNodeDef] = []
        for kind, payload in events:
            if kind == WingDecodeKind.NODE_DEF and isinstance(payload, WingNodeDef):
                collected.append(payload)
                handled.append(payload)
            elif kind == WingDecodeKind.NODE_DATA and isinstance(payload, WingNodeData):
                handled.append(payload)
            elif (
                kind == WingDecodeKind.REQUEST_END
                and pending_req is not None
                and not pending_req.future.done()
            ):
                pending_req.future.set_result(collected)
        return handled

    def _begin_stale_node_def_drain(self) -> None:
        if self._discard_node_defs_until_end:
            return
        self._discard_node_defs_until_end = True
        loop = asyncio.get_running_loop()
        self._discard_node_defs_done = loop.create_future()

    async def _wait_for_stale_node_def_drain(self) -> None:
        if not self._discard_node_defs_until_end:
            return
        done = self._discard_node_defs_done
        if done is None:
            self._begin_stale_node_def_drain()
            done = self._discard_node_defs_done
        assert done is not None
        try:
            await asyncio.wait_for(done, timeout=LIST_CHILDREN_DRAIN_TIMEOUT_SECONDS)
        except TimeoutError:
            LOGGER.warning(
                "Wing native timed out draining stale node-def response after %.1fs",
                LIST_CHILDREN_DRAIN_TIMEOUT_SECONDS,
            )
            self._finish_stale_node_def_drain()

    def _finish_stale_node_def_drain(self) -> None:
        self._discard_node_defs_until_end = False
        done = self._discard_node_defs_done
        self._discard_node_defs_done = None
        if done is not None and not done.done():
            done.set_result(None)

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
