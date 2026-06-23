import asyncio
from unittest.mock import AsyncMock

import pytest

from midijuggler.adapters.wing_native import _FEEDBACK_PUBLISH_INTERVAL_S, _FADER_SEND_INTERVAL_S, WingNativeAdapter
from midijuggler.config import parse_config
from midijuggler.datapoint.bridge import EventToDataPointBridge
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import float_value
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, OscMessageEvent
from midijuggler.device.registry import DeviceRegistry
from midijuggler.learn import resolve_osc_target_address, resolve_target_datapoint
from midijuggler.modules.io.midi import MidiIOModule
from midijuggler.modules.io.wing_native import WingNativeIOModule
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.service import MIDIJugglerService
from midijuggler.wing.native.client import WingNativeClient, WingPathBinding
from midijuggler.wing.native.decoder import WingNodeData

from conftest import make_wing_io_module, midi_device, wing_device


def test_resolve_target_datapoint_supports_wing_native_library() -> None:
    config = parse_config(
        {
            "adapters": {
                "wing_native_foh": {
                    "type": "wing_native",
                    "enabled": True,
                    "remote_host": "192.168.1.48",
                    "wing_library": "behringer_wing",
                }
            },
            "devices": [wing_device("wing_native_foh")],
        }
    )
    registry = DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter("wing_native_foh")

    assert resolve_osc_target_address(config, device, "ch_1_fdr") == "/ch/1/fdr"
    assert resolve_target_datapoint(
        config,
        target_adapter="wing_native_foh",
        target_parameter_id="ch_1_fdr",
        device_registry=registry,
    ) == "wing_native_foh./ch/1/fdr"


def test_wing_native_io_module_sends_connection_targets_by_library_id() -> None:
    async def scenario() -> int:
        config = parse_config(
            {
                "runtime": {"datapoint_routing": True},
                "adapters": {
                    "wing_native_foh": {
                        "type": "wing_native",
                        "enabled": True,
                        "remote_host": "192.168.1.48",
                        "wing_library": "behringer_wing",
                    },
                    "xtouch_mini": {
                        "type": "midi",
                        "enabled": True,
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    },
                },
                "devices": [
                    wing_device("wing_native_foh"),
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "fader-to-wing",
                        "source": "xtouch_mini.layer_a_fader",
                        "target": "wing_native_foh.ch_1_fdr",
                        "input_min": 0.0,
                        "input_max": 127.0,
                        "output_min": 0.0,
                        "output_max": 1.0,
                    }
                ],
            }
        )
        store = DataPointStore()
        bus = EventBus()
        adapter = WingNativeAdapter(
            "wing_native_foh",
            config.adapters["wing_native_foh"],
            bus,
        )
        adapter._client = WingNativeClient("192.168.1.48")  # noqa: SLF001
        adapter._client.remember_binding(WingPathBinding("/ch/1/fdr", 99))  # noqa: SLF001
        adapter._client.set_float = AsyncMock()  # type: ignore[method-assign]
        adapter.running = True

        module, _registry = make_wing_io_module(config, adapter, store, "wing_native_foh")
        await module.start()
        await store.write(float_value("wing_native_foh.ch_1_fdr", 0.25))
        await asyncio.sleep(_FADER_SEND_INTERVAL_S + 0.05)
        return adapter._client.set_float.await_count  # type: ignore[attr-defined]

    assert asyncio.run(scenario()) == 1


def test_wing_native_feedback_routes_to_xtouch_fader() -> None:
    async def scenario() -> tuple[int, int]:
        config = parse_config(
            {
                "runtime": {"datapoint_routing": True},
                "adapters": {
                    "wing_native_foh": {
                        "type": "wing_native",
                        "enabled": True,
                        "remote_host": "192.168.1.48",
                        "wing_library": "behringer_wing",
                    },
                    "xtouch_mini": {
                        "type": "midi",
                        "enabled": True,
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    },
                },
                "devices": [
                    wing_device("wing_native_foh"),
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "wing-to-fader",
                        "source": "wing_native_foh./ch/1/fdr",
                        "target": "xtouch_mini.layer_a_fader",
                        "input_min": 0.0,
                        "input_max": 1.0,
                        "output_min": 0.0,
                        "output_max": 127.0,
                    }
                ],
            }
        )
        service = MIDIJugglerService(config)
        wing = service._wing_native_adapters()["wing_native_foh"]
        wing._client = WingNativeClient("192.168.1.48")  # noqa: SLF001
        wing.running = True

        midi = service._midi_adapters()["xtouch_mini"]
        midi.send_midi_message = AsyncMock()

        await service.module_registry.start_all()
        service.event_bridge.attach()
        await service.event_bridge._on_osc_message(
            OscMessageEvent(
                source="wing_native_foh",
                address="/ch/1/fdr",
                arguments=(0.5,),
                direction="input",
                canonical_address="/ch/1/fdr",
            )
        )
        return (
            midi.send_midi_message.await_count,
            midi.send_midi_message.await_args.args[0].data[1],
        )

    count, value = asyncio.run(scenario())
    assert count == 1
    assert value == pytest.approx(64)


def test_wing_feedback_with_normalized_input_range_maps_to_midi() -> None:
    async def scenario() -> list[int]:
        config = parse_config(
            {
                "runtime": {"datapoint_routing": True},
                "adapters": {
                    "wing_native_foh": {
                        "type": "wing_native",
                        "enabled": True,
                        "remote_host": "192.168.1.48",
                        "wing_library": "behringer_wing",
                    },
                    "xtouch_mini": {
                        "type": "midi",
                        "enabled": True,
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    },
                },
                "devices": [
                    wing_device("wing_native_foh"),
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "wing-to-fader",
                        "source": "wing_native_foh./ch/1/fdr",
                        "target": "xtouch_mini.layer_a_fader",
                        "input_min": 0.0,
                        "input_max": 1.0,
                        "output_min": 0.0,
                        "output_max": 63.0,
                    },
                ],
            }
        )
        service = MIDIJugglerService(config)
        wing = service._wing_native_adapters()["wing_native_foh"]
        wing._client = WingNativeClient("192.168.1.48")  # noqa: SLF001
        wing._client.remember_binding(WingPathBinding("/ch/1/fdr", 99))  # noqa: SLF001
        wing.running = True

        midi = service._midi_adapters()["xtouch_mini"]
        midi.send_midi_message = AsyncMock()

        await service.module_registry.start_all()
        service.event_bridge.attach()

        sent: list[int] = []
        for normalized in (0.10850439071655274, 0.5, 1.0):
            await wing._publish_node_data(  # noqa: SLF001
                WingNodeData(99, float_value=normalized, float_raw=True)
            )
            await asyncio.sleep(_FEEDBACK_PUBLISH_INTERVAL_S + 0.05)
            assert midi.send_midi_message.await_count == len(sent) + 1
            sent.append(midi.send_midi_message.await_args.args[0].data[1])

        return sent

    values = asyncio.run(scenario())
    assert values[0] == pytest.approx(6.8, abs=1.0)
    assert values[1] == pytest.approx(31.5, abs=1.0)
    assert values[2] == pytest.approx(63.0, abs=1.0)
    assert len(set(round(value) for value in values)) > 1


def test_wing_feedback_with_engineering_input_range_maps_via_db() -> None:
    async def scenario() -> list[int]:
        config = parse_config(
            {
                "runtime": {"datapoint_routing": True},
                "adapters": {
                    "wing_native_foh": {
                        "type": "wing_native",
                        "enabled": True,
                        "remote_host": "192.168.1.48",
                        "wing_library": "behringer_wing",
                    },
                    "xtouch_mini": {
                        "type": "midi",
                        "enabled": True,
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    },
                },
                "devices": [
                    wing_device("wing_native_foh"),
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "wing-to-fader",
                        "source": "wing_native_foh./ch/1/fdr",
                        "target": "xtouch_mini.layer_a_fader",
                        "input_min": -90.0,
                        "input_max": 10.0,
                        "output_min": 0.0,
                        "output_max": 63.0,
                    },
                ],
            }
        )
        service = MIDIJugglerService(config)
        wing = service._wing_native_adapters()["wing_native_foh"]
        wing._client = WingNativeClient("192.168.1.48")  # noqa: SLF001
        wing._client.remember_binding(WingPathBinding("/ch/1/fdr", 99))  # noqa: SLF001
        wing.running = True

        midi = service._midi_adapters()["xtouch_mini"]
        midi.send_midi_message = AsyncMock()

        await service.module_registry.start_all()
        service.event_bridge.attach()

        sent: list[int] = []
        for normalized in (0.10850439071655274, 0.5, 1.0):
            await wing._publish_node_data(  # noqa: SLF001
                WingNodeData(99, float_value=normalized, float_raw=True)
            )
            await asyncio.sleep(_FEEDBACK_PUBLISH_INTERVAL_S + 0.05)
            assert midi.send_midi_message.await_count == len(sent) + 1
            sent.append(midi.send_midi_message.await_args.args[0].data[1])

        return sent

    values = asyncio.run(scenario())
    assert values[0] == pytest.approx(23.5, abs=1.5)
    assert values[1] == pytest.approx(50.4, abs=1.5)
    assert values[2] == pytest.approx(63.0, abs=1.0)
    assert len(set(round(value) for value in values)) > 1


def test_wing_feedback_prefers_normalized_wire_units_when_bidirectional() -> None:
    async def scenario() -> float:
        config = parse_config(
            {
                "runtime": {"datapoint_routing": True},
                "adapters": {
                    "wing_native_foh": {
                        "type": "wing_native",
                        "enabled": True,
                        "remote_host": "192.168.1.48",
                        "wing_library": "behringer_wing",
                    },
                    "xtouch_mini": {
                        "type": "midi",
                        "enabled": True,
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    },
                },
                "devices": [
                    wing_device("wing_native_foh"),
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "fader-to-wing",
                        "source": "xtouch_mini.layer_a_fader",
                        "target": "wing_native_foh./ch/1/fdr",
                        "input_min": 0.0,
                        "input_max": 63.0,
                        "output_min": 0.0,
                        "output_max": 1.0,
                    },
                    {
                        "id": "wing-to-fader",
                        "source": "wing_native_foh./ch/1/fdr",
                        "target": "xtouch_mini.layer_a_fader",
                        "input_min": -90.0,
                        "input_max": 10.0,
                        "output_min": 0.0,
                        "output_max": 63.0,
                    },
                ],
            }
        )
        store = DataPointStore()
        bus = EventBus()
        adapter = WingNativeAdapter(
            "wing_native_foh",
            config.adapters["wing_native_foh"],
            bus,
        )
        module, _registry = make_wing_io_module(config, adapter, store, "wing_native_foh")
        await module.start()

        assert adapter._fader_output_ranges["/ch/1/fdr"] == (0.0, 1.0)  # noqa: SLF001

        from midijuggler.modules.modifier.range_map import decode_wing_fader_feedback

        return decode_wing_fader_feedback(
            0.10850439071655274,
            output_min=0.0,
            output_max=1.0,
            wire_raw=True,
        )

    assert asyncio.run(scenario()) == pytest.approx(0.10850439071655274)


def test_forward_fader_move_reaches_wing_native_through_service() -> None:
    async def scenario() -> float:
        config = parse_config(
            {
                "runtime": {"datapoint_routing": True},
                "adapters": {
                    "wing_native_foh": {
                        "type": "wing_native",
                        "enabled": True,
                        "remote_host": "192.168.1.48",
                        "wing_library": "behringer_wing",
                    },
                    "xtouch_mini": {
                        "type": "midi",
                        "enabled": True,
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                        "midi_library": "behringer_xtouch_mini",
                    },
                },
                "devices": [
                    wing_device("wing_native_foh"),
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
                "connections": [
                    {
                        "id": "fader-to-wing",
                        "source": "xtouch_mini.layer_a_fader",
                        "target": "wing_native_foh./ch/1/fdr",
                        "input_min": 0.0,
                        "input_max": 127.0,
                        "output_min": 0.0,
                        "output_max": 1.0,
                    }
                ],
            }
        )
        service = MIDIJugglerService(config)
        wing = service._wing_native_adapters()["wing_native_foh"]
        wing._client = WingNativeClient("192.168.1.48")  # noqa: SLF001
        wing._client.remember_binding(WingPathBinding("/ch/1/fdr", 99))  # noqa: SLF001
        wing._client.set_float = AsyncMock()  # type: ignore[method-assign]
        wing.running = True

        await service.module_registry.start_all()
        service.event_bridge.attach()
        await service.event_bridge._on_control(
            ControlEvent(source="xtouch_mini", control="layer_a_fader", value=64.0)
        )
        await asyncio.sleep(_FADER_SEND_INTERVAL_S + 0.05)
        return wing._client.set_float.await_args.args[1]  # type: ignore[union-attr]

    sent_value = asyncio.run(scenario())
    assert sent_value == pytest.approx(0.5039370078740157)
