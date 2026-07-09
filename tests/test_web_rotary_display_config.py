import asyncio
from pathlib import Path

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
from midijuggler.web.server import WebInterface


def test_rotary_display_config_payload_includes_device_section() -> None:
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
    assert payload["enabled"] is True
    assert payload["serial_port"] == "/dev/ttyACM0"
    assert payload["device"]["host"] == "midijuggler.local"
    assert payload["device"]["wifi_pass"] == "secret"
    assert payload["device"]["beat_led_color"] == "#FF4400"


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
    )
    interface.bind_rotary_display_module(module)

    result = asyncio.run(
        interface.apply_rotary_display_config(
            {
                "device": {
                    "host": "192.168.1.20",
                    "wifi_pass": "new-pass",
                }
            }
        )
    )

    saved = load_config(config_file)
    assert result["persisted"] is True
    assert saved.rotary_display.device.host == "192.168.1.20"
    assert saved.rotary_display.device.wifi_pass == "new-pass"
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
    )
    interface.bind_rotary_display_module(module)

    result = asyncio.run(
        interface.apply_rotary_display_config(
            {
                "transport": "osc",
            }
        )
    )

    assert result["persisted"] is True
    assert enable_calls == [True]
    assert module.config.transport == "osc"
