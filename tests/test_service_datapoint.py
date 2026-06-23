import asyncio

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent
from midijuggler.master_clock import MasterClock
from midijuggler.mapping import MappingRule
from midijuggler.service import MIDIJugglerService


def test_service_skips_legacy_mapping_when_datapoint_routing_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "adapters": {"gpio": {"enabled": False}},
            "mappings": [
                {
                    "id": "test",
                    "source": "gpio:pin17",
                    "target": "midi:cc:1:64",
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
        await service._map_control(
            ControlEvent(source="gpio", control="pin17", value=1.0)
        )

    asyncio.run(scenario())
    assert published == []
    assert service.mapping is None


def test_service_uses_mapping_engine_when_legacy_routing_enabled() -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": False},
            "adapters": {"gpio": {"enabled": False}},
            "mappings": [
                {
                    "id": "test",
                    "source": "gpio:pin17",
                    "target": "midi:cc:1:64",
                }
            ],
        }
    )
    service = MIDIJugglerService(config)
    assert service.mapping is not None
    assert len(service.mapping.rules) == 1


def test_build_module_registry_includes_gpio_datapoints() -> None:
    config = parse_config(
        {
            "adapters": {
                "gpio": {
                    "enabled": True,
                    "pins": [17],
                    "active_low": True,
                }
            }
        }
    )
    service = MIDIJugglerService(config)

    async def scenario() -> None:
        await service.module_registry.start_all()

    asyncio.run(scenario())
    specs = service.datapoint_store.registry_snapshot()
    assert any(entry["id"] == "gpio.pin17" for entry in specs)
