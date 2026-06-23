import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from midijuggler.adapters.hid import EV_KEY, HidAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AdapterConfig, load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


class FakeHidReader:
    def read_one(self):
        return None

    def close(self) -> None:
        return None

    def initial_values(self) -> dict[tuple[int, int], int]:
        return {}


@pytest.fixture
def fake_evdev_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(name: str) -> tuple[int, int]:
        mapping = {"BTN_A": (EV_KEY, 304)}
        normalized = str(name).strip().upper()
        if normalized not in mapping:
            raise ValueError(f"unknown evdev code: {name!r}")
        return mapping[normalized]

    monkeypatch.setattr("midijuggler.adapters.hid.resolve_evdev_code", resolve)
    monkeypatch.setattr("midijuggler.web.server.hid_available", lambda: True)
    devices = [
        {
            "path": "/dev/input/event0",
            "name": "Test Gamepad",
            "vendor_id": "0x046d",
            "product_id": "0xc21f",
        }
    ]
    monkeypatch.setattr("midijuggler.web.server.list_input_devices", lambda: devices)
    monkeypatch.setattr("midijuggler.hid.codes.list_input_devices", lambda: devices)


def test_hid_adapters_config_payload_lists_instances(fake_evdev_codes: None) -> None:
    config = parse_config(
        {
            "adapters": {
                "gamepad": {
                    "type": "hid",
                    "enabled": True,
                    "vendor_id": "0x046d",
                    "product_id": "0xc21f",
                    "inputs": [{"code": "BTN_A", "control": "btn_a"}],
                }
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.hid_adapters_config_payload()

    assert payload["hid_available"] is True
    assert payload["available_devices"][0]["path"] == "/dev/input/event0"
    assert len(payload["instances"]) == 1
    instance = payload["instances"][0]
    assert instance["name"] == "gamepad"
    assert instance["vendor_id"] == "0x046d"
    assert instance["product_id"] == "0xc21f"
    assert instance["device_name"] == "Test Gamepad"
    assert instance["device_key"] == "0x046d:0xc21f"
    assert instance["resolved_device"] == "/dev/input/event0"
    assert instance["inputs"][0]["code"] == "BTN_A"


def test_apply_hid_adapters_config_persists_section(
    tmp_path: Path,
    fake_evdev_codes: None,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.gamepad]
        type = "hid"
        enabled = false
        device = "/dev/input/event0"
        codes = ["BTN_A"]
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    bus = EventBus()
    adapter = HidAdapter(
        name="gamepad",
        config=config.adapters["gamepad"],
        bus=bus,
        reader_factory=lambda _device_path, _inputs: FakeHidReader(),
    )
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        hid_adapters={"gamepad": adapter},
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_hid_adapters_config(
            {
                "instances": [
                    {
                        "name": "gamepad",
                        "enabled": True,
                        "vendor_id": "0x046d",
                        "product_id": "0xc21f",
                        "device_key": "0x046d:0xc21f",
                        "inputs": [
                            {
                                "code": "BTN_A",
                                "control": "button_a",
                                "value_min": 0.0,
                                "value_max": 1.0,
                            }
                        ],
                    }
                ],
                "deleted": [],
            }
        )
    )

    saved = load_config(config_file)
    gamepad = next(
        instance for instance in result["instances"] if instance["name"] == "gamepad"
    )
    assert gamepad["inputs"][0]["control"] == "button_a"
    assert gamepad["vendor_id"] == "0x046d"
    assert gamepad["product_id"] == "0xc21f"
    assert gamepad["device_name"] == "Test Gamepad"
    saved_options = saved.adapters["gamepad"].options
    assert saved_options["vendor_id"] == "0x046d"
    assert saved_options["product_id"] == "0xc21f"
    assert "device" not in saved_options
    assert saved_options["inputs"][0]["control"] == "button_a"
    assert "vendor_id" in config_file.read_text(encoding="utf-8")
    assert "device =" not in config_file.read_text(encoding="utf-8")


def test_apply_hid_adapters_config_allows_enabled_without_inputs(
    fake_evdev_codes: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def patched_hid_adapter(*args, **kwargs):
        kwargs.setdefault("reader_factory", lambda _device_path, _inputs: FakeHidReader())
        return HidAdapter(*args, **kwargs)

    monkeypatch.setattr("midijuggler.web.server.HidAdapter", patched_hid_adapter)

    config = parse_config({"adapters": {}})
    bus = EventBus()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
    )

    result = asyncio.run(
        interface.apply_hid_adapters_config(
            {
                "instances": [
                    {
                        "name": "encoder_key",
                        "enabled": True,
                        "vendor_id": "0x046d",
                        "product_id": "0xc21f",
                        "device_key": "0x046d:0xc21f",
                        "inputs": [],
                    }
                ],
                "deleted": [],
            }
        )
    )

    instance = next(item for item in result["instances"] if item["name"] == "encoder_key")
    assert instance["enabled"] is True
    assert instance["vendor_id"] == "0x046d"
    assert instance["product_id"] == "0xc21f"
    assert instance["device_name"] == "Test Gamepad"
    assert instance["inputs"] == []
    assert interface.hid_adapters["encoder_key"].running is True


def test_apply_hid_adapters_config_migrates_legacy_device_path(
    tmp_path: Path,
    fake_evdev_codes: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def patched_hid_adapter(*args, **kwargs):
        kwargs.setdefault("reader_factory", lambda _device_path, _inputs: FakeHidReader())
        return HidAdapter(*args, **kwargs)

    monkeypatch.setattr("midijuggler.web.server.HidAdapter", patched_hid_adapter)

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.gamepad]
        type = "hid"
        enabled = true
        device = "/dev/input/event0"
        codes = ["BTN_A"]
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_hid_adapters_config(
            {
                "instances": [
                    {
                        "name": "gamepad",
                        "enabled": True,
                        "device": "/dev/input/event0",
                        "inputs": [{"code": "BTN_A", "control": "btn_a"}],
                    }
                ],
                "deleted": [],
            }
        )
    )

    instance = next(item for item in result["instances"] if item["name"] == "gamepad")
    assert instance["vendor_id"] == "0x046d"
    assert instance["product_id"] == "0xc21f"
    saved = load_config(config_file)
    assert saved.adapters["gamepad"].options["vendor_id"] == "0x046d"
    assert "device" not in saved.adapters["gamepad"].options


def test_apply_hid_learn_mode_activates_adapter(
    fake_evdev_codes: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse_config(
        {
            "adapters": {
                "gamepad": {
                    "type": "hid",
                    "enabled": True,
                    "device": "/dev/input/event0",
                    "inputs": [{"code": "BTN_A", "control": "btn_a"}],
                }
            }
        }
    )
    bus = EventBus()
    adapter = HidAdapter(
        name="gamepad",
        config=config.adapters["gamepad"],
        bus=bus,
        reader_factory=lambda _device_path, _inputs: FakeHidReader(),
    )
    adapter.set_learn_active = AsyncMock()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        hid_adapters={"gamepad": adapter},
    )
    monkeypatch.setattr(adapter, "running", True)

    payload = asyncio.run(
        interface.apply_hid_learn_mode({"name": "gamepad", "active": True})
    )

    adapter.set_learn_active.assert_awaited_once_with(True)
    assert payload["learn_active"] == "gamepad"
