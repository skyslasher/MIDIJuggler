from midijuggler.config import parse_config
from midijuggler.datapoint.types import ModifierKind

from conftest import gpio_device, midi_device


def test_default_datapoint_routing_is_true() -> None:
    config = parse_config({})
    assert config.runtime.datapoint_routing is True


def test_parse_runtime_and_connections() -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "adapters": {
                "gpio": {"enabled": True, "pins": [17]},
                "midi": {"enabled": True},
            },
            "devices": [
                gpio_device(),
                midi_device("midi", adapter="midi"),
            ],
            "connections": [
                {
                    "id": "gpio-to-midi",
                    "source": "gpio.pin17",
                    "target": "midi.cc_0_64",
                    "modifier": "range_map",
                    "input_min": 0.0,
                    "input_max": 1.0,
                    "output_min": 0.0,
                    "output_max": 127.0,
                }
            ],
        }
    )
    assert config.runtime.datapoint_routing is True
    assert len(config.connections) == 1
    assert config.connections[0].modifier == ModifierKind.RANGE_MAP


def test_parse_connection_enabled_defaults_true() -> None:
    config = parse_config(
        {
            "devices": [gpio_device(), midi_device("midi", adapter="midi")],
            "connections": [
                {
                    "id": "gpio-to-midi",
                    "source": "gpio.pin17",
                    "target": "midi.cc_0_64",
                }
            ],
        }
    )
    assert config.connections[0].enabled is True


def test_parse_connection_enabled_false() -> None:
    config = parse_config(
        {
            "devices": [gpio_device(), midi_device("midi", adapter="midi")],
            "connections": [
                {
                    "id": "gpio-to-midi",
                    "source": "gpio.pin17",
                    "target": "midi.cc_0_64",
                    "enabled": False,
                }
            ],
        }
    )
    assert config.connections[0].enabled is False
