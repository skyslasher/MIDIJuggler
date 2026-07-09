import pytest

from midijuggler.datapoint.bridge import (
    connection_from_legacy_mapping,
    legacy_source_to_datapoint,
    legacy_target_to_datapoint,
    mapping_from_connection,
    migrate_mappings_to_connections,
)
from midijuggler.datapoint.migrate import stored_connections
from midijuggler.device.registry import DeviceRegistry
from midijuggler.mapping import MappingRule


def test_legacy_source_to_datapoint() -> None:
    assert legacy_source_to_datapoint("gpio:pin17") == "gpio.pin17"


def test_legacy_target_to_datapoint_for_midi_cc() -> None:
    assert legacy_target_to_datapoint("midi:cc:1:64") == "midi.cc_1_64"


def test_legacy_target_to_datapoint_for_osc_address() -> None:
    assert legacy_target_to_datapoint("desk:/ch/01/mix/level") == "desk./ch/01/mix/level"


def test_control_bridge_maps_clock_parameters_without_device() -> None:
    import asyncio

    from midijuggler.config import parse_config
    from midijuggler.datapoint.bridge import EventToDataPointBridge
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.eventbus import EventBus
    from midijuggler.events import ControlEvent

    config = parse_config({"adapters": {}})
    store = DataPointStore()
    registry = DeviceRegistry.from_config(config)
    bridge = EventToDataPointBridge(store, EventBus(), registry)

    async def scenario() -> dict[str, float | None]:
        await bridge._on_control(ControlEvent(source="clock", control="bpm", value=120.0))
        await bridge._on_control(
            ControlEvent(source="clock", control="quarter_ms", value=500.0)
        )
        return {
            str(entry.point_id): entry.float_value
            for entry in store.history()
            if entry.float_value is not None
        }

    values = asyncio.run(scenario())
    assert values["clock.bpm"] == pytest.approx(120.0)
    assert values["clock.quarter_ms"] == pytest.approx(500.0)


def test_osc_bridge_skips_unbound_adapter_without_crash() -> None:
    import asyncio

    from midijuggler.config import parse_config
    from midijuggler.datapoint.bridge import EventToDataPointBridge
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.eventbus import EventBus
    from midijuggler.events import OscMessageEvent

    config = parse_config(
        {
            "adapters": {
                "osc": {"enabled": True, "type": "osc", "host": "127.0.0.1", "port": 9000},
            },
        }
    )
    store = DataPointStore()
    # Pi rotary setups often use the osc adapter without a bound device entry.
    registry = DeviceRegistry({}, config.adapters)
    bridge = EventToDataPointBridge(store, EventBus(), registry)

    async def scenario() -> None:
        await bridge._on_osc_message(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/rotary/hello",
                arguments=("rotary-267248.local", 9001),
                direction="input",
            )
        )
        await bridge._on_osc_message(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/clock/bpm",
                arguments=(128.0,),
                direction="input",
            )
        )

    asyncio.run(scenario())
    assert store.history() == []


def test_osc_bridge_maps_wing_feedback_to_canonical_datapoint() -> None:
    import asyncio

    from midijuggler.config import parse_config
    from midijuggler.datapoint.bridge import EventToDataPointBridge
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.eventbus import EventBus
    from midijuggler.events import OscMessageEvent

    from conftest import wing_device

    config = parse_config(
        {
            "adapters": {"wing_foh": {"enabled": True, "type": "wing_native"}},
            "devices": [wing_device("wing_foh")],
        }
    )
    store = DataPointStore()
    registry = DeviceRegistry.from_config(config)
    bridge = EventToDataPointBridge(store, EventBus(), registry)
    bridge.attach()

    async def scenario() -> list[float | None]:
        await bridge._on_osc_message(
            OscMessageEvent(
                source="wing_foh",
                address="/ch/1/fdr~~~",
                arguments=("-oo", 0.0, -144.0),
                direction="input",
                canonical_address="/ch/1/fdr",
            )
        )
        return [
            entry.float_value
            for entry in store.history()
            if str(entry.point_id) == "wing_foh./ch/1/fdr" and entry.float_value is not None
        ]

    values = asyncio.run(scenario())
    assert values == [pytest.approx(0.0)]


def test_connection_from_legacy_mapping() -> None:
    rule = MappingRule(
        id="test",
        source="gpio:pin17",
        target="midi:cc:1:64",
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=127.0,
        invert=True,
    )
    connection = connection_from_legacy_mapping(rule)
    assert connection.source == "gpio.pin17"
    assert connection.target == "midi.cc_1_64"
    assert connection.invert is True


def test_migrate_mappings_to_connections() -> None:
    rules = [
        MappingRule(
            id="a",
            source="gpio:pin17",
            target="osc.desk:/fader",
        )
    ]
    connections = migrate_mappings_to_connections(rules)
    assert len(connections) == 1
    assert connections[0].id == "a"


def test_mapping_from_connection_roundtrip() -> None:
    rule = MappingRule(
        id="test",
        source="gpio:pin17",
        target="midi:cc:1:64",
        input_min=0.0,
        input_max=1.0,
        output_min=10.0,
        output_max=100.0,
        invert=True,
    )
    connection = connection_from_legacy_mapping(rule)
    restored = mapping_from_connection(connection)
    assert restored == rule


def test_stored_connections_returns_explicit_connections() -> None:
    from midijuggler.datapoint.types import ConnectionSpec

    explicit = [
        ConnectionSpec(
            id="modern",
            source="gpio.pin18",
            target="midi.cc_1_65",
        )
    ]
    resolved = stored_connections(explicit)
    assert len(resolved) == 1
    assert resolved[0].id == "modern"


def _assert_osc_custom_point_routes_to_clock_bpm(
    *,
    custom_point_id: str,
    connection_source: str,
    osc_address: str,
    expected_bpm: float,
) -> None:
    import asyncio

    from midijuggler.config import parse_config
    from midijuggler.datapoint.bridge import EventToDataPointBridge
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.datapoint.types import ConnectionSpec, ModifierKind
    from midijuggler.device.points import build_device_datapoints
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.eventbus import EventBus
    from midijuggler.events import OscMessageEvent
    from midijuggler.master_clock import MasterClock
    from midijuggler.modules.generator.master_clock import MasterClockGenerator
    from midijuggler.modules.modifier.graph import ModifierGraph

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "adapters": {
                "osc": {"enabled": True, "type": "osc", "host": "127.0.0.1", "port": 9000},
            },
            "devices": [
                {
                    "uid": "osc",
                    "name": "osc",
                    "adapter": "osc",
                    "library_kind": "osc",
                    "custom_points": [
                        {
                            "id": custom_point_id,
                            "direction": "input",
                            "protocol": "osc",
                            "value_min": 0,
                            "value_max": 500,
                        }
                    ],
                }
            ],
        }
    )
    store = DataPointStore()
    registry = DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter("osc")
    specs, _ = build_device_datapoints(device, config.adapters["osc"])
    store.register_many(specs)
    master_clock = MasterClock(config.master_clock, EventBus())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    graph = ModifierGraph(
        store,
        [
            ConnectionSpec(
                id="osc-clock-bpm",
                source=connection_source,
                target="clock.bpm_set",
                input_min=0.0,
                input_max=500.0,
                output_min=0.0,
                output_max=500.0,
            )
        ],
    )
    bridge = EventToDataPointBridge(store, EventBus(), registry)

    async def scenario() -> None:
        await clock_gen.start()
        await graph.start()
        await bridge._on_osc_message(
            OscMessageEvent(
                source="osc",
                address=osc_address,
                arguments=(expected_bpm,),
                direction="input",
            )
        )

    asyncio.run(scenario())
    assert master_clock.bpm == pytest.approx(expected_bpm)


def test_osc_custom_point_with_leading_slash_routes_to_clock_bpm_set() -> None:
    _assert_osc_custom_point_routes_to_clock_bpm(
        custom_point_id="/clock/bpm",
        connection_source="osc./clock/bpm",
        osc_address="/clock/bpm",
        expected_bpm=140.0,
    )


def test_osc_custom_point_without_leading_slash_routes_to_clock_bpm_set() -> None:
    _assert_osc_custom_point_routes_to_clock_bpm(
        custom_point_id="clock/bpm",
        connection_source="osc.clock/bpm",
        osc_address="/clock/bpm",
        expected_bpm=140.0,
    )
