"""GamePi display brightness as a data point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ValueType,
)
from midijuggler.modules.base import InterfaceModule

LOGGER = logging.getLogger(__name__)

GAMEPI_MODULE = "gamepi"
BRIGHTNESS_POINT = DataPointId(GAMEPI_MODULE, "brightness")
BRIGHTNESS_SET_POINT = DataPointId(GAMEPI_MODULE, "brightness_set")
DEFAULT_STATE_PATH = Path(
    os.environ.get("GAMEPI_BRIGHTNESS_STATE", "/var/lib/gamepi/brightness")
)
MTIME_POLL_SEC = float(os.environ.get("GAMEPI_BRIGHTNESS_WATCH_POLL_SEC", "2"))


def status_to_datapoint_value(payload: dict[str, Any]) -> DataPointValue:
    available = bool(payload.get("available"))
    level = int(payload["level"]) if available and "level" in payload else 0
    max_level = int(payload.get("max", 255))
    return DataPointValue(
        point_id=BRIGHTNESS_POINT,
        value_type=ValueType.INT,
        int_value=level,
        bool_value=available,
        float_value=float(max_level),
    )


async def publish_brightness_to_store(
    store: DataPointStore | None,
    payload: dict[str, Any] | None = None,
) -> None:
    if store is None:
        return
    if payload is None:
        from midijuggler.web import gamepi_brightness as brightness_api

        payload = brightness_api.brightness_status_payload()
    value = status_to_datapoint_value(payload)
    previous = store.snapshot().get(str(BRIGHTNESS_POINT))
    if previous is not None and previous.get("int_value") != value.int_value:
        value = replace(value, force_notify=True)
    await store.write(value)


class _LinuxInotifyWatcher:
    """Minimal inotify wrapper for a single file path."""

    IN_MODIFY = 0x00000002
    IN_CLOSE_WRITE = 0x00000008
    IN_CREATE = 0x00000100
    IN_MOVED_TO = 0x00000040
    IN_DELETE_SELF = 0x00000400
    IN_MOVE_SELF = 0x00000800
    IN_MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_CREATE | IN_MOVED_TO | IN_DELETE_SELF | IN_MOVE_SELF

    def __init__(self, path: Path) -> None:
        import ctypes
        import ctypes.util

        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        self._libc = libc
        self._path = path
        self._fd = int(libc.inotify_init1(0x800))  # IN_NONBLOCK
        if self._fd < 0:
            raise OSError("inotify_init1 failed")
        self._watch_path = path.parent if path.parent.is_dir() else path
        self._watch_name = path.name
        self._wd = int(
            libc.inotify_add_watch(
                self._fd,
                os.fsencode(str(self._watch_path)),
                self.IN_MASK,
            )
        )
        if self._wd < 0:
            os.close(self._fd)
            raise OSError("inotify_add_watch failed")

    def fileno(self) -> int:
        return self._fd

    def relevant_events(self) -> bool:
        import ctypes

        buffer = bytearray(4096)
        length = int(self._libc.read(self._fd, buffer, len(buffer)))
        if length <= 0:
            return False
        offset = 0
        while offset < length:
            event = buffer[offset : offset + 16]
            name_len = int.from_bytes(event[12:16], "little")
            name = ""
            if name_len > 0:
                raw = buffer[offset + 16 : offset + 16 + name_len]
                name = raw.split(b"\0", 1)[0].decode(errors="replace")
            mask = int.from_bytes(event[4:8], "little")
            offset += 16 + name_len
            if mask & (self.IN_DELETE_SELF | self.IN_MOVE_SELF):
                self._rewatch()
            if not name or name == self._watch_name:
                if mask & (
                    self.IN_MODIFY
                    | self.IN_CLOSE_WRITE
                    | self.IN_CREATE
                    | self.IN_MOVED_TO
                ):
                    return True
        return False

    def _rewatch(self) -> None:
        self._libc.inotify_rm_watch(self._fd, self._wd)
        self._wd = int(
            self._libc.inotify_add_watch(
                self._fd,
                os.fsencode(str(self._watch_path)),
                self.IN_MASK,
            )
        )

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1


class GamePiBrightnessModule(InterfaceModule):
    """Publish GamePi brightness to the data-point store and watch state file changes."""

    def __init__(
        self,
        store: DataPointStore,
        *,
        state_path: Path | None = None,
    ) -> None:
        super().__init__(GAMEPI_MODULE, store)
        self.state_path = state_path or DEFAULT_STATE_PATH
        self._watch_task: asyncio.Task[None] | None = None
        self._inotify: _LinuxInotifyWatcher | None = None
        self._last_mtime_ns: int | None = None

    def datapoints(self) -> list[DataPointSpec]:
        return [
            DataPointSpec(
                id=BRIGHTNESS_POINT,
                value_type=ValueType.INT,
                direction=DataPointDirection.INPUT,
                label="GamePi display brightness",
                value_min=0,
                value_max=255,
                protocol="gamepi",
                category="display",
            ),
            DataPointSpec(
                id=BRIGHTNESS_SET_POINT,
                value_type=ValueType.INT,
                direction=DataPointDirection.OUTPUT,
                label="Set GamePi display brightness",
                value_min=0,
                value_max=255,
                protocol="gamepi",
                category="display",
            ),
        ]

    async def start(self) -> None:
        await super().start()
        self.store.subscribe(BRIGHTNESS_SET_POINT, self._on_brightness_set)
        await self.refresh()
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        if self._watch_task is not None:
            self._watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None
        if self._inotify is not None:
            self._inotify.close()
            self._inotify = None
        await super().stop()

    async def refresh(self) -> None:
        await publish_brightness_to_store(self.store)
        with contextlib.suppress(OSError):
            self._last_mtime_ns = self.state_path.stat().st_mtime_ns

    async def _on_brightness_set(self, value: DataPointValue) -> None:
        if value.int_value is not None:
            requested = value.int_value
        elif value.float_value is not None:
            requested = int(round(value.float_value))
        else:
            return

        current = self.store.snapshot().get(str(BRIGHTNESS_POINT))
        if current is not None and current.get("int_value") == requested:
            return

        from midijuggler.web import gamepi_brightness as brightness_api

        result = brightness_api.set_brightness_payload(requested)
        if not result.get("available"):
            LOGGER.warning("brightness_set ignored: backend unavailable")
            return
        await publish_brightness_to_store(self.store, result)

    async def _watch_loop(self) -> None:
        if sys.platform == "linux":
            with contextlib.suppress(OSError):
                self._inotify = _LinuxInotifyWatcher(self.state_path)
        loop = asyncio.get_running_loop()
        try:
            while self.running:
                if self._inotify is not None:
                    await self._wait_inotify(loop)
                else:
                    await self._poll_mtime()
        finally:
            if self._inotify is not None:
                self._inotify.close()
                self._inotify = None

    async def _wait_inotify(self, loop: asyncio.AbstractEventLoop) -> None:
        assert self._inotify is not None
        future: asyncio.Future[None] = loop.create_future()

        def _on_readable() -> None:
            if not future.done():
                future.set_result(None)

        loop.add_reader(self._inotify.fileno(), _on_readable)
        try:
            await future
            if self._inotify.relevant_events():
                await self.refresh()
        finally:
            loop.remove_reader(self._inotify.fileno())

    async def _poll_mtime(self) -> None:
        await asyncio.sleep(MTIME_POLL_SEC)
        try:
            mtime_ns = self.state_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        if mtime_ns != self._last_mtime_ns:
            self._last_mtime_ns = mtime_ns
            await self.refresh()
