"""GamePi display brightness as a data point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from midijuggler.config import GamePiConfig
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

        payload = brightness_api.brightness_status_payload(fresh=True)
    value = status_to_datapoint_value(payload)
    previous = store.snapshot().get(str(BRIGHTNESS_POINT))
    if previous is not None and previous.get("int_value") != value.int_value:
        value = replace(value, force_notify=True)
    await store.write(value)


class GamePiBrightnessModule(InterfaceModule):
    """Publish GamePi brightness to the data-point store and watch state file changes."""

    def __init__(
        self,
        store: DataPointStore,
        *,
        config: GamePiConfig | None = None,
        state_path: Path | None = None,
    ) -> None:
        super().__init__(GAMEPI_MODULE, store)
        self.config = config or GamePiConfig()
        self.state_path = Path(state_path or self.config.brightness_state_path or DEFAULT_STATE_PATH)
        self._watch_task: asyncio.Task[None] | None = None
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
        await super().stop()

    def update_config(self, config: GamePiConfig) -> None:
        self.config = config
        self.state_path = Path(config.brightness_state_path)

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
        while self.running:
            await self._poll_mtime()

    async def _poll_mtime(self) -> None:
        await asyncio.sleep(max(self.config.brightness_poll_sec, 0.1))
        try:
            mtime_ns = self.state_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        if mtime_ns != self._last_mtime_ns:
            self._last_mtime_ns = mtime_ns
            await self.refresh()
