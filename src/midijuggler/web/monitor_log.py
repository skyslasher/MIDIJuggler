"""Forward Python log records to the monitor event bus."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from midijuggler.events import LogEvent

if TYPE_CHECKING:
    from midijuggler.eventbus import EventBus

LOGGER = logging.getLogger(__name__)


class MonitorLogHandler(logging.Handler):
    """Publish midijuggler log records as LogEvent on the event bus."""

    def __init__(self, bus: EventBus, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._bus = bus
        self._loop = loop
        self._queue: asyncio.Queue[logging.LogRecord] = asyncio.Queue(maxsize=500)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="monitor-log-handler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == LOGGER.name:
            return
        try:
            self._loop.call_soon_threadsafe(self._enqueue, record)
        except RuntimeError:
            return

    def _enqueue(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            return

    async def _run(self) -> None:
        while True:
            record = await self._queue.get()
            try:
                await self._bus.publish(
                    LogEvent(
                        source="log",
                        level=record.levelname,
                        message=record.getMessage(),
                        logger=record.name,
                    )
                )
            except Exception:
                LOGGER.exception("monitor log handler failed")
