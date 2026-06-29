import asyncio
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from midijuggler.adapters.gpio import GpioAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface

from conftest import gpio_device, midi_custom_point, midi_device, osc_device


def _interface(config_path: Path) -> WebInterface:
    config = load_config(config_path)
    return WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_path,
    )


def test_devices_api_lists_adapter_options(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[adapters.gpio]
enabled = true
pins = [17]

[adapters.x32_foh]
type = "osc"
enabled = true
osc_library = "behringer_x32"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def scenario() -> dict:
        interface = _interface(config_path)
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/api/devices")
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert len(payload["devices"]) >= 2
    names = {entry["name"] for entry in payload["adapter_options"]}
    assert "gpio" in names
    assert "x32_foh" in names


def test_devices_api_persists_devices(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[adapters.gpio]
enabled = true
pins = [17]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def scenario() -> dict:
        interface = _interface(config_path)
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/devices",
                json={"devices": [gpio_device("foot_switches", adapter="gpio")]},
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert payload["persisted"] is True
    assert payload["devices"][0]["uid"] == "foot_switches"
    assert payload["devices"][0]["name"] == "foot_switches"
    saved = load_config(config_path)
    assert saved.devices["foot_switches"].adapter == "gpio"


def test_devices_api_rejects_duplicate_adapter_binding(tmp_path) -> None:
    config = parse_config(
        {
            "adapters": {
                "x32_foh": {"type": "osc", "enabled": True, "osc_library": "behringer_x32"},
            },
            "devices": [osc_device("x32_foh", "behringer_x32")],
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    async def scenario() -> int:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/devices",
                json={
                    "devices": [
                        osc_device("desk_a", "behringer_x32", adapter="x32_foh"),
                        osc_device("desk_b", "behringer_x32", adapter="x32_foh"),
                    ]
                },
            )
            return response.status

    assert asyncio.run(scenario()) == 400


def test_set_devices_config_refreshes_gpio_datapoints(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[adapters.gpio]
enabled = true
pins = [17]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    store = DataPointStore()
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        gpio_adapter=GpioAdapter("gpio", config.adapters["gpio"], EventBus()),
        datapoint_store=store,
        config_path=config_path,
    )

    async def scenario() -> list[dict]:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            before = await (await client.get("/api/datapoints")).json()
            assert not any(
                entry["id"].startswith("foot_switches.")
                for entry in before["datapoints"]
            )

            response = await client.post(
                "/api/devices",
                json={"devices": [gpio_device("foot_switches", adapter="gpio")]},
            )
            assert response.status == 200

            after = await (await client.get("/api/datapoints")).json()
            return after["datapoints"]

    datapoints = asyncio.run(scenario())
    assert any(entry["id"] == "foot_switches.pin17" for entry in datapoints)


def test_set_devices_config_refreshes_midi_custom_points() -> None:
    config = parse_config(
        {
            "adapters": {"midi": {"enabled": True}},
            "devices": [],
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

    async def scenario() -> list[dict]:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/devices",
                json={
                    "devices": [
                        {
                            **midi_device("midi_controller", adapter="midi"),
                            "custom_points": [midi_custom_point("cc_1_64")],
                        }
                    ]
                },
            )
            assert response.status == 200
            payload = await (await client.get("/api/datapoints")).json()
            return payload["datapoints"]

    datapoints = asyncio.run(scenario())
    assert any(entry["id"] == "midi_controller.cc_1_64" for entry in datapoints)


def test_set_devices_config_unregisters_removed_device_datapoints(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[adapters.gpio]
enabled = true
pins = [17]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    store = DataPointStore()
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        gpio_adapter=GpioAdapter("gpio", config.adapters["gpio"], EventBus()),
        datapoint_store=store,
        config_path=config_path,
    )

    async def scenario() -> list[dict]:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/devices",
                json={"devices": [gpio_device("foot_switches", adapter="gpio")]},
            )
            assert response.status == 200

            response = await client.post("/api/devices", json={"devices": []})
            assert response.status == 200

            payload = await (await client.get("/api/datapoints")).json()
            return payload["datapoints"]

    datapoints = asyncio.run(scenario())
    assert not any(entry["id"].startswith("foot_switches.") for entry in datapoints)


def test_devices_api_persists_xtouch_feedback_settings(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[adapters.xtouch_mini]
enabled = true
type = "midi"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def scenario() -> dict:
        interface = _interface(config_path)
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/devices",
                json={
                    "devices": [
                        {
                            **midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                            "adapter": "xtouch_mini",
                            "feedback_refresh_interval": 2.0,
                            "midi_value_channel": 5,
                            "midi_display_channel": 9,
                        }
                    ]
                },
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    device = payload["devices"][0]
    assert device["feedback_refresh_interval"] == 2.0
    assert device["midi_value_channel"] == 5
    assert device["midi_display_channel"] == 9
    saved = load_config(config_path)
    saved_device = saved.devices["xtouch_mini"]
    assert saved_device.feedback_refresh_interval == 2.0
    assert saved_device.midi_value_channel == 5
    assert saved_device.midi_display_channel == 9


def test_devices_api_rejects_xtouch_feedback_for_other_libraries(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[adapters.midi]
enabled = true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def scenario() -> int:
        interface = _interface(config_path)
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/devices",
                json={
                    "devices": [
                        {
                            **midi_device("midi_controller", adapter="midi", library="presonus_faderport"),
                            "feedback_refresh_interval": 1.0,
                        }
                    ]
                },
            )
            return response.status

    assert asyncio.run(scenario()) == 400
