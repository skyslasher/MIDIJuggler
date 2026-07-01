import asyncio

import pytest

from midijuggler.adapters.hid import EV_KEY
from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent
from midijuggler.service import MIDIJugglerService

from conftest import gpio_device, hid_device, midi_device


@pytest.fixture
def fake_evdev_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(name: str) -> tuple[int, int]:
        if str(name).strip().upper() == "BTN_A":
            return EV_KEY, 304
        raise ValueError(f"unknown evdev code: {name!r}")

    monkeypatch.setattr("midijuggler.adapters.hid.resolve_evdev_code", resolve)


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


def test_service_registers_osc_custom_datapoints_for_disabled_adapter() -> None:
    config = parse_config(
        {
            "adapters": {
                "osc_custom": {
                    "type": "osc",
                    "enabled": False,
                    "host": "127.0.0.1",
                    "port": 10023,
                },
            },
            "devices": [
                {
                    "uid": "desk_custom",
                    "name": "Custom OSC Desk",
                    "adapter": "osc_custom",
                    "library_kind": "osc",
                    "custom_points": [
                        {"id": "/custom/fader", "direction": "bidirectional"},
                    ],
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
    assert any(entry["id"] == "desk_custom./custom/fader" for entry in specs)


def test_service_routes_osc_custom_point_to_master_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "master_clock": {"enabled": True, "bpm": 120.0},
            "adapters": {
                "osc": {"enabled": True, "type": "osc", "host": "127.0.0.1", "port": 9000},
            },
            "devices": [
                {
                    "uid": "osc_bridge",
                    "name": "OSC Bridge",
                    "adapter": "osc",
                    "library_kind": "osc",
                    "custom_points": [
                        {
                            "id": "/clock/bpm",
                            "value_type": "int",
                            "direction": "input",
                            "value_min": 0,
                            "value_max": 500,
                        }
                    ],
                }
            ],
            "connections": [
                {
                    "id": "osc-clock-bpm",
                    "source": "osc./clock/bpm",
                    "target": "clock.bpm_set",
                    "input_min": 0.0,
                    "input_max": 500.0,
                    "output_min": 0.0,
                    "output_max": 500.0,
                }
            ],
        }
    )
    service = MIDIJugglerService(config)

    async def fake_start(adapter) -> None:
        adapter.running = True

    async def fake_stop(adapter) -> None:
        adapter.running = False

    for adapter in service.adapters:
        monkeypatch.setattr(adapter, "start", lambda adapter=adapter: fake_start(adapter))
        monkeypatch.setattr(adapter, "stop", lambda adapter=adapter: fake_stop(adapter))

    async def scenario() -> None:
        await service.start()
        from midijuggler.events import OscMessageEvent

        await service.event_bridge._on_osc_message(
            OscMessageEvent(
                source="osc",
                address="/clock/bpm",
                arguments=(140,),
                direction="input",
            )
        )

    asyncio.run(scenario())
    assert service.master_clock.bpm == pytest.approx(140.0)
    assert service.config.connections[0].source == "osc_bridge./clock/bpm"


def test_osc_bpm_routing_works_again_after_tap_tempo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from midijuggler.events import OscMessageEvent

    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "master_clock": {
                "enabled": True,
                "bpm": 120.0,
                "tap_tempo_min_taps": 3,
            },
            "adapters": {
                "osc": {"enabled": True, "type": "osc", "host": "127.0.0.1", "port": 9000},
            },
            "devices": [
                {
                    "uid": "osc_bridge",
                    "name": "OSC Bridge",
                    "adapter": "osc",
                    "library_kind": "osc",
                    "custom_points": [
                        {
                            "id": "/clock/bpm",
                            "value_type": "int",
                            "direction": "input",
                            "value_min": 0,
                            "value_max": 500,
                        }
                    ],
                }
            ],
            "connections": [
                {
                    "id": "osc-clock-bpm",
                    "source": "osc_bridge./clock/bpm",
                    "target": "clock.bpm_set",
                    "input_min": 0.0,
                    "input_max": 500.0,
                    "output_min": 0.0,
                    "output_max": 500.0,
                }
            ],
        }
    )
    service = MIDIJugglerService(config)

    async def fake_start(adapter) -> None:
        adapter.running = True

    async def fake_stop(adapter) -> None:
        adapter.running = False

    for adapter in service.adapters:
        monkeypatch.setattr(adapter, "start", lambda adapter=adapter: fake_start(adapter))
        monkeypatch.setattr(adapter, "stop", lambda adapter=adapter: fake_stop(adapter))

    async def send_osc_bpm(value: int) -> None:
        await service.event_bridge._on_osc_message(
            OscMessageEvent(
                source="osc",
                address="/clock/bpm",
                arguments=(value,),
                direction="input",
            )
        )

    async def tap_tempo_to_125() -> None:
        from midijuggler.datapoint.types import DataPointId, DataPointValue, ValueType

        tap = DataPointId("clock", "tap_tempo")
        for timestamp in (10.0, 10.48, 10.96, 11.44):
            await service.datapoint_store.write(
                DataPointValue(
                    point_id=tap,
                    value_type=ValueType.TRIGGER,
                    bool_value=False,
                    timestamp=timestamp,
                )
            )
            await service.datapoint_store.write(
                DataPointValue(
                    point_id=tap,
                    value_type=ValueType.TRIGGER,
                    bool_value=True,
                    timestamp=timestamp,
                )
            )

    async def scenario() -> None:
        await service.start()
        await send_osc_bpm(130)
        assert service.master_clock.bpm == pytest.approx(130.0)
        await tap_tempo_to_125()
        assert service.master_clock.bpm == pytest.approx(125.0)
        await send_osc_bpm(130)
        assert service.master_clock.bpm == pytest.approx(130.0)

    asyncio.run(scenario())


def test_service_registers_hid_datapoints_for_disabled_adapter(fake_evdev_codes: None) -> None:
    config = parse_config(
        {
            "adapters": {
                "gamepad": {
                    "type": "hid",
                    "enabled": False,
                    "device": "/dev/input/event0",
                    "codes": ["BTN_A"],
                },
            },
            "devices": [hid_device("gamepad")],
        }
    )
    service = MIDIJugglerService(config)

    async def scenario() -> None:
        await service.module_registry.start_all()
        await service.web.refresh_all_device_datapoints()

    asyncio.run(scenario())
    specs = service.datapoint_store.registry_snapshot()
    assert any(entry["id"] == "gamepad.btn_a" for entry in specs)
