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
    monkeypatch.setattr(
        "midijuggler.web.server.list_input_devices",
        lambda: [
            {
                "path": "/dev/input/event0",
                "name": "Test Gamepad",
                "vendor_id": "0x046d",
                "product_id": "0xc21f",
            }
        ],
    )


def test_hid_adapters_config_payload_lists_instances(fake_evdev_codes: None) -> None:
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
    assert payload["instances"][0]["name"] == "gamepad"
    assert payload["instances"][0]["inputs"][0]["code"] == "BTN_A"


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
                        "device": "/dev/input/event0",
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
    assert saved.adapters["gamepad"].options["inputs"][0]["control"] == "button_a"
    assert "[[adapters.gamepad.inputs]]" in config_file.read_text(encoding="utf-8")


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
                        "device": "/dev/input/event0",
                        "inputs": [],
                    }
                ],
                "deleted": [],
            }
        )
    )

    instance = next(item for item in result["instances"] if item["name"] == "encoder_key")
    assert instance["enabled"] is True
    assert instance["device"] == "/dev/input/event0"
    assert instance["inputs"] == []
    assert interface.hid_adapters["encoder_key"].running is True


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
