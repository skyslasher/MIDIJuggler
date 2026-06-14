import pytest

from midijuggler.config import AdapterConfig, parse_config
from midijuggler.midi.library_match import build_source_index
from midijuggler.midi.target_encode import encode_mapped_midi_target
from midijuggler.midi.xtouch_channels import (
    DEFAULT_XTOUCH_DISPLAY_CHANNEL,
    DEFAULT_XTOUCH_VALUE_CHANNEL,
    parse_midi_channel_option,
    resolve_parameter_midi_channel,
    xtouch_display_channel,
    xtouch_value_channel,
)
from midijuggler.midi_library import get_midi_library


def _xtouch_adapter(**options: object) -> AdapterConfig:
    return AdapterConfig(
        enabled=True,
        options={"midi_library": "behringer_xtouch_mini", **options},
        kind="midi",
    )


def test_parse_midi_channel_option_defaults_and_validates() -> None:
    assert parse_midi_channel_option(None, field_name="midi_value_channel", default=11) == 11
    assert parse_midi_channel_option(5, field_name="midi_value_channel", default=11) == 5

    with pytest.raises(ValueError, match="between 1 and 16"):
        parse_midi_channel_option(0, field_name="midi_value_channel", default=11)


def test_xtouch_channel_helpers_read_adapter_options() -> None:
    adapter = _xtouch_adapter(
        midi_value_channel=3,
        midi_display_channel=7,
    )

    assert xtouch_value_channel(adapter) == 3
    assert xtouch_display_channel(adapter) == 7


def test_resolve_parameter_midi_channel_splits_value_and_display_targets() -> None:
    library = get_midi_library("behringer_xtouch_mini")
    parameters = {parameter.id: parameter for parameter in library.parameters}
    adapter = _xtouch_adapter(midi_value_channel=5, midi_display_channel=9)

    assert (
        resolve_parameter_midi_channel(adapter, parameters["layer_a_encoder_1_turn"])
        == 5
    )
    assert (
        resolve_parameter_midi_channel(adapter, parameters["layer_a_encoder_1_value"])
        == 5
    )
    assert (
        resolve_parameter_midi_channel(adapter, parameters["layer_a_encoder_1_led_ring"])
        == 9
    )


def test_build_source_index_uses_configured_xtouch_value_channel() -> None:
    library = get_midi_library("behringer_xtouch_mini")
    adapter = _xtouch_adapter(midi_value_channel=6)

    index = build_source_index(library, adapter=adapter)
    matches = index.match(0xB5, (1, 64))

    assert matches
    assert matches[0].control_id == "layer_a_encoder_1_turn"


def test_encode_mapped_midi_target_uses_configured_xtouch_channels() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                    "midi_value_channel": 4,
                    "midi_display_channel": 8,
                }
            }
        }
    )

    value_status, value_data = encode_mapped_midi_target(
        config,
        "xtouch_mini",
        "layer_a_encoder_1_value",
        64.0,
    )
    ring_status, ring_data = encode_mapped_midi_target(
        config,
        "xtouch_mini",
        "layer_a_encoder_1_led_ring",
        5.0,
    )

    assert value_status == 0xB3
    assert value_data == (1, 64)
    assert ring_status == 0xB7
    assert ring_data == (1, 5)


def test_xtouch_channel_defaults_match_library() -> None:
    assert DEFAULT_XTOUCH_VALUE_CHANNEL == 11
    assert DEFAULT_XTOUCH_DISPLAY_CHANNEL == 12
