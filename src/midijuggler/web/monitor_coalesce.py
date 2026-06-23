"""Coalesce high-rate monitor payloads before WebSocket broadcast."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from midijuggler.events import ControlEvent, Event, MidiMessageEvent, OscMessageEvent

_MONITOR_INTERVAL_S = 0.1
_FADER_MARKER = re.compile(r"(?:/fdr\b|_fader(?:_\d+)?$)", re.IGNORECASE)

FlushCallback = Callable[[dict[str, Any]], Awaitable[None]]


def monitor_event_key(event: Event) -> str | None:
    if isinstance(event, OscMessageEvent):
        if event.direction != "input" or event.echo_suppressed:
            return None
        address = event.canonical_address or event.address
        if not _FADER_MARKER.search(address):
            return None
        return f"osc:{event.source}:{address}"
    if isinstance(event, ControlEvent):
        if not _FADER_MARKER.search(event.control):
            return None
        return f"control:{event.source}:{event.control}"
    if isinstance(event, MidiMessageEvent):
        if event.direction != "output" or event.feedback_refresh:
            return None
        if event.status & 0xF0 != 0xB0 or not event.data:
            return None
        channel = event.status & 0x0F
        return f"midi-out:{event.source}:{channel}:{event.data[0]}"
    return None


def monitor_datapoint_key(payload: dict[str, Any]) -> str | None:
    point_id = str(payload.get("id", ""))
    if not point_id or not _FADER_MARKER.search(point_id):
        return None
    if payload.get("value_type") != "float":
        return None
    return f"datapoint:{point_id}"


class MonitorCoalescer:
    """Hold high-rate monitor payloads and flush them at a capped rate."""

    def __init__(self, interval_s: float = _MONITOR_INTERVAL_S) -> None:
        self._interval = max(0.01, interval_s)
        self._pending: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def close(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        for task in self._tasks.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._pending.clear()

    async def offer(
        self,
        key: str,
        payload: dict[str, Any],
        flush: FlushCallback,
        *,
        immediate: bool = False,
    ) -> None:
        if immediate:
            await flush(payload)
            return
        self._pending[key] = payload
        if key in self._tasks and not self._tasks[key].done():
            return
        self._tasks[key] = asyncio.create_task(
            self._flush_later(key, flush),
            name=f"monitor-coalesce-{key}",
        )

    async def _flush_later(self, key: str, flush: FlushCallback) -> None:
        started = time.monotonic()
        try:
            await asyncio.sleep(self._interval)
            payload = self._pending.pop(key, None)
            if payload is not None:
                await flush(payload)
        finally:
            self._tasks.pop(key, None)
            elapsed = time.monotonic() - started
            if key in self._pending:
                delay = max(0.0, self._interval - elapsed)
                if delay:
                    await asyncio.sleep(delay)
                payload = self._pending.pop(key, None)
                if payload is not None:
                    await flush(payload)
                if key in self._pending:
                    self._tasks[key] = asyncio.create_task(
                        self._flush_later(key, flush),
                        name=f"monitor-coalesce-{key}",
                    )
