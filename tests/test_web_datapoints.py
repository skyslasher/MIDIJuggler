import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface

from conftest import gpio_device, midi_custom_point, midi_device

BASE_DEVICES_TOML = """
[adapters.gpio]
enabled = true
pins = [17, 18]

[adapters.midi]
enabled = true

[[devices]]
id = "gpio"
adapter = "gpio"
library_kind = "gpio"

[[devices]]
id = "midi"
adapter = "midi"
library_kind = "midi"

[[devices.custom_points]]
id = "cc_1_64"

[[devices.custom_points]]
id = "cc_1_65"
"""


def test_datapoints_api_returns_registry() -> None:
    config = parse_config(
        {
            "adapters": {"osc": {"enabled": True}},
            "devices": [{"id": "osc", "adapter": "osc", "library_kind": "osc"}],
        }
    )
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


def test_connections_api_includes_stored_connections() -> None:
    config = parse_config(
        {
            "adapters": {
                "gpio": {"enabled": True, "pins": [17]},
                "midi": {"enabled": True},
            },
            "devices": [
                gpio_device(),
                {
                    **midi_device("midi", adapter="midi"),
                    "custom_points": [midi_custom_point("cc_1_64")],
                },
            ],
            "connections": [
                {
                    "id": "test",
                    "source": "gpio.pin17",
                    "target": "midi.cc_1_64",
                }
            ],
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
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[web]
host = "127.0.0.1"
port = 8080
{BASE_DEVICES_TOML}
[[connections]]
id = "old"
source = "gpio.pin17"
target = "midi.cc_1_64"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
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

    status = interface._status_payload()
    assert status["stored_connections"][0]["source"] == "gpio.pin18"
    assert "devices" in status

    reloaded = load_config(config_path)
    assert reloaded.connections[0].id == "updated"
    assert reloaded.connections[0].source == "gpio.pin18"


def test_set_connections_config_persists_enabled_flag(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[web]
host = "127.0.0.1"
port = 8080
{BASE_DEVICES_TOML}
[[connections]]
id = "route"
source = "gpio.pin17"
target = "midi.cc_1_64"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
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
                            "id": "route",
                            "source": "gpio.pin17",
                            "target": "midi.cc_1_64",
                            "modifier": "range_map",
                            "input_min": 0.0,
                            "input_max": 1.0,
                            "output_min": 0.0,
                            "output_max": 127.0,
                            "enabled": False,
                        }
                    ]
                },
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert payload["stored_connections"][0]["enabled"] is False

    reloaded = load_config(config_path)
    assert reloaded.connections[0].enabled is False
    assert "enabled = false" in config_path.read_text(encoding="utf-8").lower()


def test_delete_all_connections_clears_runtime_routing(tmp_path) -> None:
    from midijuggler.modules.modifier.graph import ModifierGraph

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[web]
host = "127.0.0.1"
port = 8080
{BASE_DEVICES_TOML}
[[connections]]
id = "route"
source = "gpio.pin17"
target = "midi.cc_1_64"
modifier = "range_map"
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
    store = DataPointStore()
    graph = ModifierGraph(store, config.connections)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        datapoint_store=store,
        modifier_graph=graph,
        config_path=config_path,
    )

    async def scenario() -> None:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/api/connections", json={"connections": []})
            assert response.status == 200

    asyncio.run(scenario())

    assert interface._stored_connections() == []
    assert graph.connections == []


def test_connections_api_includes_feedback_suppress_ms() -> None:
    config = parse_config({"runtime": {"feedback_suppress_ms": 750}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.connections_payload()

    assert payload["feedback_suppress_ms"] == 750


def test_set_connections_config_persists_feedback_suppress_ms(tmp_path) -> None:
    from midijuggler.modules.modifier.graph import ModifierGraph

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[runtime]
datapoint_routing = true
feedback_suppress_ms = 500
{BASE_DEVICES_TOML}
[[connections]]
id = "route"
source = "gpio.pin17"
target = "midi.cc_1_64"
modifier = "range_map"
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
    store = DataPointStore()
    graph = ModifierGraph(store, config.connections, feedback_suppress_ms=500)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        datapoint_store=store,
        modifier_graph=graph,
        config_path=config_path,
    )

    async def scenario() -> dict:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/connections",
                json={
                    "connections": [config.connections[0].as_dict()],
                    "feedback_suppress_ms": 900,
                },
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())

    assert payload["persisted"] is True
    assert payload["feedback_suppress_ms"] == 900
    assert interface.config.runtime.feedback_suppress_ms == 900
    assert graph._feedback_suppressor._window_seconds == pytest.approx(0.9)

    reloaded = load_config(config_path)
    assert reloaded.runtime.feedback_suppress_ms == 900


def test_reverse_connection_api_creates_feedback_mapping(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

[adapters.xtouch_mini]
type = "midi"
enabled = true
midi_library = "behringer_xtouch_mini"

[adapters.x32_foh]
type = "osc"
enabled = true
osc_library = "behringer_x32"

[[devices]]
id = "xtouch_mini"
adapter = "xtouch_mini"
library = "behringer_xtouch_mini"
library_kind = "midi"

[[devices]]
id = "x32_foh"
adapter = "x32_foh"
library = "behringer_x32"
library_kind = "osc"

[[connections]]
id = "encoder-to-fader"
source = "xtouch_mini.layer_a_encoder_1_turn"
target = "x32_foh./ch/01/mix/fader"
modifier = "range_map"
input_min = 1.0
input_max = 127.0
output_min = 0.0
output_max = 1.0
invert = false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_path,
    )

    async def scenario() -> dict:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/connections/reverse",
                json={"id": "encoder-to-fader"},
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())

    assert payload["persisted"] is True
    assert len(payload["stored_connections"]) == 2
    feedback = payload["created_connection"]
    assert feedback["source"] == "x32_foh./ch/01/mix/fader"
    assert feedback["target"] == "xtouch_mini.layer_a_encoder_1_value"
    assert feedback["input_min"] == 0.0
    assert feedback["input_max"] == 1.0
    assert feedback["output_min"] == 1.0
    assert feedback["output_max"] == 127.0

    reloaded = load_config(config_path)
    assert len(reloaded.connections) == 2
