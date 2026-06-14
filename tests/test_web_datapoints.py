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
    assert len(payload["stored_connections"]) == 1
    assert payload["stored_connections"][0]["id"] == "test"


def test_set_connections_config_updates_runtime_and_persists(tmp_path) -> None:
    from midijuggler.config import load_config
    from midijuggler.mapping import MappingEngine

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

[[mappings]]
id = "old"
source = "gpio:pin17"
target = "midi:cc:1:64"
input_min = 0.0
input_max = 1.0
output_min = 0.0
output_max = 127.0
invert = false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    mapping_engine = MappingEngine(config.mappings)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        mapping_engine=mapping_engine,
        config_path=config_path,
    )

    async def scenario() -> dict:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/connections",
                json={
                    "connections": [
                        {
                            "id": "updated",
                            "source": "gpio.pin18",
                            "target": "midi.cc_1_65",
                            "modifier": "range_map",
                            "input_min": 0.0,
                            "input_max": 1.0,
                            "output_min": 0.0,
                            "output_max": 127.0,
                            "invert": False,
                        }
                    ]
                },
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert payload["persisted"] is True
    assert payload["stored_connections"][0]["id"] == "updated"
    assert len(mapping_engine.rules) == 1
    assert mapping_engine.rules[0].source == "gpio:pin18"

    status = interface._status_payload()
    assert status["stored_connections"][0]["source"] == "gpio.pin18"

    reloaded = load_config(config_path)
    assert reloaded.connections[0].id == "updated"
    assert reloaded.mappings[0].source == "gpio:pin18"
