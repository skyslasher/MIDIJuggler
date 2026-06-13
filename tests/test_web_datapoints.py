import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_datapoints_api_returns_registry() -> None:
    config = parse_config({"adapters": {"osc": {"enabled": True}}})
    store = DataPointStore()
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        datapoint_store=store,
    )

    async def scenario() -> dict:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/api/datapoints")
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert "datapoints" in payload
    assert "values" in payload


def test_connections_api_includes_legacy_mappings() -> None:
    config = parse_config(
        {
            "mappings": [
                {
                    "id": "test",
                    "source": "gpio:pin17",
                    "target": "midi:cc:1:64",
                }
            ]
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.connections_payload()
    assert len(payload["connections"]) == 1
    assert payload["connections"][0]["source"] == "gpio.pin17"
