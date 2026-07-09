"""Coalesce high-rate monitor payloads before WebSocket broadcast."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from midijuggler.events import ControlEvent, Event, LogEvent, MidiMessageEvent, OscMessageEvent


def _normalize_hello_arguments(arguments: tuple[Any, ...] | list[Any]) -> tuple[Any, ...]:
    if len(arguments) < 2:
        return tuple(arguments)
    host = str(arguments[0])
    port = arguments[1]
    if isinstance(port, (int, float)) and not isinstance(port, bool):
        return (host, int(port))
    return tuple(arguments)

_MONITOR_INTERVAL_S = 0.1
_FADER_MARKER = re.compile(r"(?:/fdr\b|_fader(?:_\d+)?$)", re.IGNORECASE)
_ROTARY_REGISTERED_RE = re.compile(
    r"rotary display (?:re-)?registered at ([^:]+):(\d+)"
)

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


class MonitorEventFilter:
    """Suppress repetitive monitor payloads such as periodic rotary hello."""

    def __init__(self, hello_address: str = "/midijuggler/rotary/hello") -> None:
        self._hello_address = hello_address
        self._last_hello: tuple[str, tuple[Any, ...]] | None = None
        self._last_registered: tuple[str, int] | None = None

    def suppress(self, event: Event | dict[str, Any]) -> bool:
        kind = event.kind if isinstance(event, Event) else str(event.get("kind", ""))
        if kind == "OscMessageEvent":
            return self._suppress_rotary_hello(event)
        if kind == "ControlEvent":
            return self._suppress_rotary_hello_control(event)
        if kind == "LogEvent":
            return self._suppress_rotary_registration_log(event)
        return False

    def _suppress_rotary_hello(self, event: Event | dict[str, Any]) -> bool:
        if isinstance(event, OscMessageEvent):
            direction = event.direction
            address = event.address
            canonical_address = event.canonical_address or event.address
            arguments = tuple(event.arguments)
        else:
            direction = str(event.get("direction", "input"))
            address = str(event.get("address", ""))
            canonical_address = str(
                event.get("canonical_address", "") or event.get("address", "")
            )
            arguments = tuple(event.get("arguments") or [])
        if direction != "input":
            return False
        if address != self._hello_address and canonical_address != self._hello_address:
            return False
        key = (canonical_address, _normalize_hello_arguments(arguments))
        if key == self._last_hello:
            return True
        self._last_hello = key
        return False

    def _suppress_rotary_hello_control(self, event: Event | dict[str, Any]) -> bool:
        """Suppress hello ControlEvents; OSC adapter mirrors port as numeric value."""
        if isinstance(event, ControlEvent):
            control = event.control
        else:
            control = str(event.get("control", ""))
        if control != self._hello_address:
            return False
        return True

    def _suppress_rotary_registration_log(self, event: Event | dict[str, Any]) -> bool:
        if isinstance(event, LogEvent):
            message = event.message
        else:
            message = str(event.get("message", ""))
        match = _ROTARY_REGISTERED_RE.search(message)
        if match is None:
            return False
        if "re-registered" in message:
            return True
        host = match.group(1)
        port = int(match.group(2))
        key = (host, port)
        if key == self._last_registered:
            return True
        self._last_registered = key
        return False


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
