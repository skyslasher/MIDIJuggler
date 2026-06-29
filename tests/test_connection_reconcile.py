from midijuggler.config import parse_config
from midijuggler.datapoint.disconnected import disconnected_endpoint
from midijuggler.datapoint.reconcile import apply_module_removal_to_connections
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind

from conftest import gpio_device, midi_device, osc_device


def test_parse_config_accepts_disconnected_connection_endpoints() -> None:
    placeholder = disconnected_endpoint()
    config = parse_config(
        {
            "devices": [gpio_device(), midi_device("midi", adapter="midi")],
            "connections": [
                {
                    "id": "orphaned-target",
                    "source": "gpio.pin17",
                    "target": placeholder,
                    "enabled": False,
                }
            ],
        },
        strict=True,
    )

    assert config.connections[0].target == placeholder
    assert config.connections[0].enabled is False


def test_apply_module_removal_disconnects_endpoints_without_replacement() -> None:
    connections = [
        ConnectionSpec(
            id="wing-fader",
            source="gpio.pin17",
            target="wing_desk.ch_1_fdr",
            modifier=ModifierKind.RANGE_MAP,
        )
    ]

    updated = apply_module_removal_to_connections(connections, "wing_desk", None)

    assert updated[0].target == disconnected_endpoint()
    assert updated[0].enabled is False
    assert updated[0].source == "gpio.pin17"


def test_apply_module_removal_remaps_to_compatible_device_when_point_exists() -> None:
    connections = [
        ConnectionSpec(
            id="wing-fader",
            source="gpio.pin17",
            target="wing_a.ch_1_fdr",
            modifier=ModifierKind.RANGE_MAP,
        )
    ]

    def point_available(module: str, point: str) -> bool:
        return module == "wing_b" and point == "ch_1_fdr"

    updated = apply_module_removal_to_connections(
        connections,
        "wing_a",
        "wing_b",
        point_available=point_available,
    )

    assert updated[0].target == "wing_b.ch_1_fdr"
    assert updated[0].enabled is True
