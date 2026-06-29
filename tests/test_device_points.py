from midijuggler.config import parse_config
from midijuggler.device.points import build_device_datapoints

from conftest import wing_device


def test_wing_device_datapoints_include_library_category() -> None:
    config = parse_config(
        {
            "adapters": {
                "wing_foh": {
                    "type": "osc",
                    "enabled": True,
                    "osc_library": "behringer_wing",
                }
            },
            "devices": [wing_device("wing_foh")],
        }
    )
    device = config.devices["wing_foh"]
    adapter = config.adapters["wing_foh"]

    specs, _output_points = build_device_datapoints(device, adapter)
    by_id = {str(spec.id): spec for spec in specs}

    assert by_id["wing_foh./ch/1/fdr"].category == "channel"
    assert by_id["wing_foh./ch/1/send/1/lvl"].category == "send"
    assert by_id["wing_foh./fx/1/fxmix"].category == "fx"
    assert by_id["wing_foh./fx/2/dcy"].category == "fx_reverb"


def test_midi_library_datapoints_include_category() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": True,
                    "midi_library": "behringer_xtouch_mini",
                }
            },
            "devices": [
                {
                    "id": "xtouch_mini",
                    "adapter": "xtouch_mini",
                    "library": "behringer_xtouch_mini",
                    "library_kind": "midi",
                }
            ],
        }
    )
    device = config.devices["xtouch_mini"]
    adapter = config.adapters["xtouch_mini"]

    specs, _output_points = build_device_datapoints(device, adapter)
    encoder = next(spec for spec in specs if spec.id.point == "layer_a_encoder_1_turn")

    assert encoder.category == "encoder"
