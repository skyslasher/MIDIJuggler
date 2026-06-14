from midijuggler.datapoint.bridge import (
    connection_from_legacy_mapping,
    legacy_source_to_datapoint,
    legacy_target_to_datapoint,
    mapping_from_connection,
    migrate_mappings_to_connections,
)
from midijuggler.datapoint.migrate import resolved_user_connections, stored_connections
from midijuggler.mapping import MappingRule


def test_legacy_source_to_datapoint() -> None:
    assert legacy_source_to_datapoint("gpio:pin17") == "gpio.pin17"


def test_legacy_target_to_datapoint_for_midi_cc() -> None:
    assert legacy_target_to_datapoint("midi:cc:1:64") == "midi.cc_1_64"


def test_legacy_target_to_datapoint_for_osc_address() -> None:
    assert legacy_target_to_datapoint("desk:/ch/01/mix/level") == "desk./ch/01/mix/level"


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


def test_stored_connections_prefers_explicit_connections() -> None:
    rules = [
        MappingRule(
            id="legacy",
            source="gpio:pin17",
            target="midi:cc:1:64",
        )
    ]
    from midijuggler.datapoint.types import ConnectionSpec

    explicit = [
        ConnectionSpec(
            id="modern",
            source="gpio.pin18",
            target="midi.cc_1_65",
        )
    ]
    resolved = stored_connections(rules, explicit)
    assert len(resolved) == 1
    assert resolved[0].id == "modern"


def test_resolved_user_connections_honors_cleared_state() -> None:
    rules = [
        MappingRule(
            id="legacy",
            source="gpio:pin17",
            target="midi:cc:1:64",
        )
    ]

    assert resolved_user_connections([], []) == []
    assert len(resolved_user_connections(rules, [])) == 1
