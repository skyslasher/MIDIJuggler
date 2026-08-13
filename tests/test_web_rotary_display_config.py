import asyncio
from pathlib import Path

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config, rotary_display_instance_id
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
from midijuggler.web.server import WebInterface


def test_rotary_display_config_payload_includes_instances() -> None:
    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "transport": "both",
                "serial_port": "/dev/ttyACM0",
                "device": {
                    "transport": "both",
                    "host": "midijuggler.local",
                    "wifi_pass": "secret",
                    "beat_led_color": "#FF4400",
                },
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )
    payload = interface.rotary_display_config_payload()
    assert len(payload["instances"]) == 1
    instance = payload["instances"][0]
    assert instance["enabled"] is True
    assert instance["serial_port"] == "/dev/ttyACM0"
    assert instance["device"]["host"] == "midijuggler.local"
    assert instance["device"]["wifi_pass"] == "secret"
    assert instance["device"]["beat_led_color"] == "#FF4400"
    assert "available_serial_ports" in payload


def test_apply_rotary_display_config_persists_and_updates_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [rotary_display]
        enabled = true
        transport = "serial"
        serial_port = "/dev/ttyACM0"

        [rotary_display.device]
        transport = "both"
        host = "midijuggler.local"
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    bus = EventBus()
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._serial_connected = True
    push_calls: list[bool] = []

    async def fake_push(*, force: bool = False) -> dict:
        push_calls.append(force)
        return {"pushed": True, "fingerprint": "abc"}

    monkeypatch.setattr(module, "push_device_config", fake_push)

    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        master_clock,
        config_path=config_file,
        datapoint_store=store,
    )
    asyncio.run(module.start())
    interface.bind_rotary_display_module(module)

    result = asyncio.run(
        interface.apply_rotary_display_config(
            {
                "instances": [
                    {
                        "name": "default",
                        "enabled": True,
                        "transport": "serial",
                        "serial_port": "/dev/ttyACM0",
                        "device": {
                            "host": "192.168.1.20",
                            "wifi_pass": "new-pass",
                        },
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)
    assert result["persisted"] is True
    assert saved.rotary_displays[0].device.host == "192.168.1.20"
    assert saved.rotary_displays[0].device.wifi_pass == "new-pass"
    assert push_calls == [True]
    assert module.config.device.host == "192.168.1.20"


def test_apply_rotary_display_config_host_transport_switch_enables_osc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [rotary_display]
        enabled = true
        transport = "serial"
        serial_port = "/dev/ttyACM0"

        [rotary_display.device]
        transport = "both"
        host = "midijuggler.local"
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    bus = EventBus()
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._serial_connected = True
    enable_calls: list[bool] = []

    async def fake_enable(self) -> None:
        enable_calls.append(True)

    async def fake_push(*, force: bool = False) -> dict:
        return {"pushed": True}

    monkeypatch.setattr(RotaryDisplayModule, "_enable_host_osc_transport", fake_enable)
    monkeypatch.setattr(module, "push_device_config", fake_push)

    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        master_clock,
        config_path=config_file,
        datapoint_store=store,
    )
    asyncio.run(module.start())
    interface.bind_rotary_display_module(module)

    result = asyncio.run(
        interface.apply_rotary_display_config(
            {
                "instances": [
                    {
                        "name": "default",
                        "enabled": True,
                        "transport": "osc",
                        "serial_port": "/dev/ttyACM0",
                    }
                ]
            }
        )
    )

    assert result["persisted"] is True
    assert enable_calls == [True]
    assert module.config.transport == "osc"


def test_apply_rotary_display_config_starts_new_enabled_instance_at_runtime() -> None:
    config = parse_config({"master_clock": {"enabled": True}})
    bus = EventBus()
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, bus)
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        master_clock,
        datapoint_store=store,
    )

    async def scenario() -> None:
        result = await interface.apply_rotary_display_config(
            {
                "instances": [
                    {
                        "name": "Rotary Rack",
                        "enabled": True,
                        "transport": "serial",
                        "serial_port": "/dev/ttyACM0",
                    }
                ]
            }
        )
        assert result["restart_required"] is False
        assert "rotary_display:Rotary Rack" in interface._rotary_display_modules
        module = interface._rotary_display_modules["rotary_display:Rotary Rack"]
        assert module.config.name == "Rotary Rack"
        assert module.running is True
        await module.stop()

    asyncio.run(scenario())


def test_apply_rotary_display_push_activates_saved_instance() -> None:
    config = parse_config(
        {
            "master_clock": {"enabled": True},
            "rotary_displays": [
                {
                    "name": "Rotary Rack",
                    "enabled": True,
                    "transport": "serial",
                    "serial_port": "/dev/ttyACM0",
                }
            ],
        }
    )
    bus = EventBus()
    store = DataPointStore()
    master_clock = MasterClock(config.master_clock, bus)
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        master_clock,
        datapoint_store=store,
    )
    push_calls: list[str] = []

    async def fake_push(*, force: bool = False) -> dict:
        push_calls.append("push")
        return {"pushed": False, "reason": "serial not connected"}

    async def scenario() -> None:
        await interface.reconcile_rotary_display_modules(config.rotary_displays)
        module = interface._rotary_display_modules["rotary_display:Rotary Rack"]
        module.push_device_config = fake_push  # type: ignore[method-assign]
        response = await interface.apply_rotary_display_push({"name": "Rotary Rack"})
        assert response["push_result"]["reason"] == "serial not connected"
        assert push_calls == ["push"]
        await module.stop()

    asyncio.run(scenario())


def test_parse_multiple_rotary_displays() -> None:
    config = parse_config(
        {
            "rotary_displays": [
                {
                    "name": "main",
                    "enabled": True,
                    "serial_port": "/dev/ttyACM0",
                },
                {
                    "name": "side",
                    "enabled": True,
                    "serial_port": "/dev/ttyACM1",
                },
            ]
        }
    )
    assert len(config.rotary_displays) == 2
    assert config.rotary_displays[0].name == "main"
    assert config.rotary_displays[1].serial_port == "/dev/ttyACM1"
    assert rotary_display_instance_id(config.rotary_displays[1]) == "rotary_display:side"
