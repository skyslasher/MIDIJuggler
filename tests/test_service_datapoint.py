import asyncio

import pytest

from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent
from midijuggler.service import MIDIJugglerService

from conftest import gpio_device, midi_device


def test_service_routes_through_datapoint_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "adapters": {
                "gpio": {"enabled": False},
                "midi": {"enabled": False},
            },
            "devices": [
                gpio_device(),
                midi_device("midi", adapter="midi"),
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
    service = MIDIJugglerService(config)
    published: list[object] = []

    async def capture_many(events):
        published.extend(events)

    monkeypatch.setattr(service.bus, "publish_many", capture_many)

    async def scenario() -> None:
        await service.bus.publish(
            ControlEvent(source="gpio", control="pin17", value=1.0)
        )

    asyncio.run(scenario())
    assert service.web.modifier_graph is not None


def test_build_module_registry_includes_gpio_datapoints() -> None:
    config = parse_config(
        {
            "adapters": {
                "gpio": {
                    "enabled": True,
                    "pins": [17],
                    "active_low": True,
                }
            },
            "devices": [gpio_device()],
        }
    )
    service = MIDIJugglerService(config)

    async def scenario() -> None:
        await service.module_registry.start_all()

    asyncio.run(scenario())
    specs = service.datapoint_store.registry_snapshot()
    assert any(entry["id"] == "gpio.pin17" for entry in specs)


def test_service_registers_device_datapoints_for_disabled_midi_adapter() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": False,
                    "midi_library": "behringer_xtouch_mini",
                },
            },
            "devices": [
                {
                    "uid": "device_xtouch",
                    "name": "X-Touch Mini",
                    "adapter": "xtouch_mini",
                    "library": "behringer_xtouch_mini",
                    "library_kind": "midi",
                }
            ],
        }
    )
    service = MIDIJugglerService(config)

    async def scenario() -> None:
        await service.module_registry.start_all()
        await service.web.refresh_all_device_datapoints()

    asyncio.run(scenario())
    specs = service.datapoint_store.registry_snapshot()
    assert any(entry["id"].startswith("device_xtouch.") for entry in specs)
    assert any(
        entry["id"] == "device_xtouch.layer_a_encoder_1_turn"
        for entry in specs
    )
