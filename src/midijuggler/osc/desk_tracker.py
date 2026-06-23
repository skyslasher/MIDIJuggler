"""Background OSC desk discovery and IP relocation for bound adapter instances."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from midijuggler.osc.discovery import DiscoveredDesk, desk_identity, discover_desks

if TYPE_CHECKING:
    from midijuggler.web.server import WebInterface

LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL_SECONDS = 30.0


class OscDeskDiscoveryManager:
    """Scan the LAN for Wing/X32 desks and keep bound OSC instances reachable."""

    def __init__(
        self,
        web: WebInterface,
        *,
        interval_seconds: float = DEFAULT_SCAN_INTERVAL_SECONDS,
    ) -> None:
        self._web = web
        self._interval = max(5.0, interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._last_desks: list[DiscoveredDesk] = []

    @property
    def discovered_desks(self) -> list[dict[str, Any]]:
        return [desk.as_dict() for desk in self._last_desks]

    def remember_desks(self, desks: list[DiscoveredDesk]) -> None:
        self._last_desks = list(desks)

    async def start(self) -> None:
        await self.scan_once()
        self._task = asyncio.create_task(self._loop(), name="osc-desk-discovery")
        asyncio.create_task(self._startup_rescan(), name="osc-desk-startup-rescan")

    async def _startup_rescan(self) -> None:
        for delay in (5.0, 20.0):
            await asyncio.sleep(delay)
            try:
                await self.scan_once()
            except Exception:
                LOGGER.exception("OSC desk startup rescan failed after %.0fs", delay)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def scan_once(self) -> dict[str, Any]:
        desks = await discover_desks()
        self._last_desks = desks
        result = await self._web.sync_osc_desk_addresses(desks)
        await self._web.broadcast_status()
        if desks:
            LOGGER.info(
                "OSC desk discovery found %s desk(s): %s",
                len(desks),
                ", ".join(
                    f"{desk.protocol} {desk.ip}"
                    + (f" ({desk.name})" if desk.name else "")
                    for desk in desks
                ),
            )
        return result

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.scan_once()
            except Exception:
                LOGGER.exception("OSC desk discovery scan failed")
