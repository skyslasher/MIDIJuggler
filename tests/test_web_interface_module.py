import asyncio
from unittest.mock import AsyncMock

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import float_value
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.interface.web import WebInterfaceModule
from midijuggler.web.server import WebInterface


def test_web_interface_module_skips_emit_outputs_false() -> None:
    config = parse_config({})
    bus = EventBus()
    web = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
    )
    web.broadcast_datapoint_update = AsyncMock()
    store = DataPointStore()
    module = WebInterfaceModule(web, store)

    async def scenario() -> None:
        await module.start()
        await store.write(float_value("gpio.pin17", 1.0, emit_outputs=False))
        await store.write(float_value("gpio.pin17", 2.0))

    asyncio.run(scenario())
    assert web.broadcast_datapoint_update.await_count == 1
