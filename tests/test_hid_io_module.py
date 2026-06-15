import asyncio

import pytest

from midijuggler.adapters.hid import EV_KEY, HidAdapter
from midijuggler.config import AdapterConfig, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.modules.io.hid import HidIOModule
from midijuggler.service import MIDIJugglerService


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
        if str(name).strip().upper() == "BTN_A":
            return EV_KEY, 304
        raise ValueError(f"unknown evdev code: {name!r}")

    monkeypatch.setattr("midijuggler.adapters.hid.resolve_evdev_code", resolve)


def test_hid_io_module_registers_input_datapoints(fake_evdev_codes: None) -> None:
    bus = EventBus()
    adapter = HidAdapter(
        name="gamepad",
        config=AdapterConfig(
            enabled=True,
            options={"device": "/dev/input/event0", "codes": ["BTN_A"]},
        ),
        bus=bus,
        reader_factory=lambda _device_path, _inputs: FakeHidReader(),
    )
    module = HidIOModule(adapter, DataPointStore())

    specs = module.datapoints()

    assert len(specs) == 1
    assert str(specs[0].id) == "gamepad.btn_a"
    assert specs[0].direction.value == "input"
    assert specs[0].protocol == "hid"
    assert specs[0].value_min == pytest.approx(0.0)
    assert specs[0].value_max == pytest.approx(1.0)


def test_build_module_registry_includes_hid_datapoints(fake_evdev_codes: None) -> None:
    config = parse_config(
        {
            "adapters": {
                "gamepad": {
                    "enabled": True,
                    "type": "hid",
                    "device": "/dev/input/event0",
                    "codes": ["BTN_A"],
                }
            }
        }
    )
    service = MIDIJugglerService(config)

    async def scenario() -> None:
        await service.module_registry.start_all()

    asyncio.run(scenario())
    specs = service.datapoint_store.registry_snapshot()
    assert any(entry["id"] == "gamepad.btn_a" for entry in specs)
