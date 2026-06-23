from midijuggler.config import AdapterConfig, parse_config
from midijuggler.datapoint.clock_connections import (
    clock_output_connections,
    merge_clock_output_connections,
    usable_clock_output_targets,
)
from midijuggler.datapoint.migrate import effective_connections, stored_connections
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind

from conftest import gpio_device, midi_device


def test_clock_output_connections_builds_passthrough_links() -> None:
    connections = clock_output_connections(["midi", "rtp_midi"])

    assert len(connections) == 8
    assert connections[0] == ConnectionSpec(
        id="clock-tick-to-midi",
        source="clock.midi_tick",
        target="midi.midi_out",
        modifier=ModifierKind.PASSTHROUGH,
    )
    assert any(
        connection.target == "rtp_midi.midi_out"
        and connection.source == "clock.midi_stop"
        for connection in connections
    )


def test_merge_clock_output_connections_avoids_duplicates() -> None:
    existing = [
        ConnectionSpec(
            id="clock-tick-to-midi",
            source="clock.midi_tick",
            target="midi.midi_out",
            modifier=ModifierKind.PASSTHROUGH,
        )
    ]

    merged = merge_clock_output_connections(existing, ["midi"])

    assert len(merged) == 4
    assert sum(1 for connection in merged if connection.source == "clock.midi_tick") == 1


def test_usable_clock_output_targets_requires_configured_ports() -> None:
    from midijuggler.device.types import DeviceConfig

    adapters = {
        "midi": AdapterConfig(
            enabled=True,
            kind="midi",
            options={},
        ),
        "xtouch_mini": AdapterConfig(
            enabled=True,
            kind="midi",
            options={
                "input_port": "X-TOUCH MINI",
                "output_port": "X-TOUCH MINI",
            },
        ),
    }
    devices = {
        "midi": DeviceConfig(id="midi", adapter="midi", library_kind="midi"),
        "xtouch_mini": DeviceConfig(
            id="xtouch_mini",
            adapter="xtouch_mini",
            library="behringer_xtouch_mini",
            library_kind="midi",
        ),
    }

    assert usable_clock_output_targets(["midi", "xtouch_mini"], devices, adapters) == [
        "xtouch_mini"
    ]


def test_effective_connections_skips_clock_targets_without_ports() -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "master_clock": {"enabled": True, "output_targets": ["midi"]},
            "adapters": {"midi": {"enabled": True}},
            "devices": [midi_device("midi", adapter="midi")],
        }
    )

    connections = effective_connections(config, datapoint_routing=True)

    assert connections == []


def test_effective_connections_adds_clock_defaults_when_routing_enabled() -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "master_clock": {"enabled": True, "output_targets": ["midi"]},
            "adapters": {
                "midi": {
                    "enabled": True,
                    "output_port": "MIDIJuggler Out",
                }
            },
            "devices": [midi_device("midi", adapter="midi")],
        }
    )

    connections = effective_connections(
        config,
        datapoint_routing=config.runtime.datapoint_routing,
    )

    assert len(connections) == 4
    assert {connection.target for connection in connections} == {"midi.midi_out"}


def test_stored_connections_returns_configured_connections() -> None:
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
