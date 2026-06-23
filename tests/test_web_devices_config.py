import asyncio
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface

from conftest import gpio_device, osc_device


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
    assert payload["devices"][0]["id"] == "foot_switches"
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
