"""Web interface as a data-point interface module."""

from __future__ import annotations

from typing import Any

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointSpec, DataPointValue
from midijuggler.modules.base import InterfaceModule
from midijuggler.web.server import WebInterface


class WebInterfaceModule(InterfaceModule):
    """Expose the web UI against the data-point store."""

    def __init__(self, web: WebInterface, store: DataPointStore) -> None:
        super().__init__("web", store)
        self.web = web
        self._recent_updates: list[dict[str, Any]] = []

    def datapoints(self) -> list[DataPointSpec]:
        return []

    async def start(self) -> None:
        await super().start()
        self.store.subscribe_all(self._on_datapoint_update)
        self.web.datapoint_store = self.store

    async def stop(self) -> None:
        await super().stop()

    async def _on_datapoint_update(self, value: DataPointValue) -> None:
        if not value.emit_outputs:
            return
        payload = value.as_dict()
        self._recent_updates.append(payload)
        if len(self._recent_updates) > 200:
            self._recent_updates = self._recent_updates[-200:]
        await self.web.broadcast_datapoint_update(payload)

    def recent_updates(self) -> list[dict[str, Any]]:
        return list(self._recent_updates)
