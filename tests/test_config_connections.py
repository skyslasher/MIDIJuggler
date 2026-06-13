from midijuggler.config import parse_config
from midijuggler.datapoint.types import ModifierKind


def test_parse_runtime_and_connections() -> None:
    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "connections": [
                {
                    "id": "gpio-to-midi",
                    "source": "gpio.pin17",
                    "target": "midi.main.cc_0_64",
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
