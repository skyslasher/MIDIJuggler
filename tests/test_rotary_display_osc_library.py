from midijuggler.config import parse_config
from midijuggler.datapoint.migrate import effective_connections, implicit_connections
from midijuggler.datapoint.rotary_connections import (
    merge_rotary_display_connections,
    rotary_encoder_to_clock_connections,
)
from midijuggler.datapoint.rotary_module_feedback import (
    rotary_module_feedback_connections,
)
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind
from midijuggler.osc_library import get_osc_library, list_osc_libraries

from conftest import osc_device


def _config_with_rotary_device(*, rotary_module_enabled: bool = False) -> dict:
    return {
        "runtime": {"datapoint_routing": True},
        "master_clock": {"enabled": True, "output_targets": []},
        "adapters": {"osc": {"enabled": True, "type": "osc"}},
        "devices": [osc_device("rotary_encoder", "rotary_display", adapter="osc")],
        "connections": [],
        "rotary_display": {"enabled": rotary_module_enabled},
    }


def test_lists_rotary_display_osc_library() -> None:
    libraries = list_osc_libraries()
    assert "rotary_display" in [library.id for library in libraries]


def test_rotary_display_library_contains_clock_and_feedback_points() -> None:
    library = get_osc_library("rotary_display")
    parameters = {parameter.id: parameter for parameter in library.parameters}

    assert library.bundled is True
    assert len(library.bundled_connections) == 9
    assert parameters["clock_bpm"].address == "/midijuggler/clock/bpm"
    assert parameters["clock_bpm"].direction == "source"
    assert parameters["clock_start_stop"].address == "/midijuggler/clock/start_stop"
    assert parameters["rotary_bpm"].address == "/midijuggler/rotary/bpm"
    assert parameters["rotary_bpm"].direction == "target"
    assert parameters["rotary_running"].address == "/midijuggler/rotary/running"
    assert parameters["rotary_running"].direction == "target"
    assert parameters["rotary_click_enabled"].address == "/midijuggler/rotary/click_enabled"
    assert parameters["rotary_click_enabled"].direction == "target"
    assert parameters["rotary_click_interval"].address == "/midijuggler/rotary/click_interval"
    assert parameters["rotary_click_interval"].direction == "target"
    assert parameters["rotary_beat"].address == "/midijuggler/rotary/beat"
    assert parameters["rotary_beat"].direction == "target"
    assert parameters["rotary_hello"].category == "registration"


def test_merge_rotary_display_connections_adds_defaults() -> None:
    config = parse_config(_config_with_rotary_device())
    merged = merge_rotary_display_connections([], config.devices)

    sources = {connection.source for connection in merged}
    targets = {connection.target for connection in merged}
    assert "rotary_encoder./midijuggler/clock/bpm" in sources
    assert "clock.bpm_set" in targets
    assert "clock.beat" in sources
    assert "rotary_encoder./midijuggler/rotary/beat" in targets


def test_merge_rotary_display_connections_skips_duplicates() -> None:
    config = parse_config(_config_with_rotary_device())
    existing = [
        ConnectionSpec(
            id="existing",
            source="rotary_encoder./midijuggler/clock/bpm",
            target="clock.bpm_set",
            modifier=ModifierKind.PASSTHROUGH,
        )
    ]
    merged = merge_rotary_display_connections(existing, config.devices)
    assert sum(
        1
        for connection in merged
        if connection.source == "rotary_encoder./midijuggler/clock/bpm"
        and connection.target == "clock.bpm_set"
    ) == 1


def test_rotary_encoder_to_clock_connection_ids_are_stable() -> None:
    connections = rotary_encoder_to_clock_connections("rotary_encoder")
    assert connections[0].id == "rotary_encoder-bpm-to-clock"


def test_effective_connections_adds_rotary_defaults_when_module_disabled() -> None:
    config = parse_config(_config_with_rotary_device(rotary_module_enabled=False))
    connections = effective_connections(config)
    assert any(
        connection.source == "rotary_encoder./midijuggler/clock/bpm"
        and connection.target == "clock.bpm_set"
        for connection in connections
    )


def test_effective_connections_adds_encoder_defaults_when_module_enabled() -> None:
    config = parse_config(_config_with_rotary_device(rotary_module_enabled=True))
    connections = effective_connections(config)
    assert any(
        connection.source == "rotary_encoder./midijuggler/clock/bpm"
        and connection.target == "clock.bpm_set"
        for connection in connections
    )
    assert not any(
        connection.target == "rotary_encoder./midijuggler/rotary/bpm"
        for connection in connections
    )


def test_effective_connections_skips_rotary_device_feedback_when_module_enabled() -> None:
    config = parse_config(_config_with_rotary_device(rotary_module_enabled=True))
    connections = effective_connections(config)
    assert not any(
        connection.target.startswith("rotary_encoder./midijuggler/rotary/")
        for connection in connections
    )


def test_effective_connections_adds_module_feedback_when_module_enabled() -> None:
    config = parse_config(_config_with_rotary_device(rotary_module_enabled=True))
    connections = effective_connections(config)
    expected = {(connection.source, connection.target) for connection in rotary_module_feedback_connections()}
    actual = {(connection.source, connection.target) for connection in connections}
    assert expected.issubset(actual)


def test_implicit_connections_exposes_managed_rotary_bundles() -> None:
    config = parse_config(_config_with_rotary_device(rotary_module_enabled=True))
    implicit = implicit_connections(config)
    assert implicit
    assert all(connection.managed_by for connection in implicit)
    assert any(connection.managed_by == "rotary_display" for connection in implicit)
    assert any(connection.managed_by == "rotary_display:module" for connection in implicit)
    assert not any(
        connection.target == "rotary_encoder./midijuggler/rotary/bpm"
        for connection in implicit
    )


def test_implicit_connections_omit_user_stored_duplicates() -> None:
    config = parse_config(
        {
            **_config_with_rotary_device(rotary_module_enabled=False),
            "connections": [
                {
                    "id": "manual-bpm",
                    "source": "rotary_encoder./midijuggler/clock/bpm",
                    "target": "clock.bpm_set",
                    "modifier": "passthrough",
                }
            ],
        }
    )
    implicit = implicit_connections(config)
    assert not any(
        connection.source == "rotary_encoder./midijuggler/clock/bpm"
        and connection.target == "clock.bpm_set"
        for connection in implicit
    )
