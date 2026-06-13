import pytest

from midijuggler.config import parse_config
from midijuggler.midi.target_encode import (
    encode_midi_target_message,
    lookup_midi_target_ranges,
    resolve_midi_target_parameter,
)
from midijuggler.midi_library import get_midi_library


def _parameter(library_id: str, parameter_id: str):
    library = get_midi_library(library_id)
    return next(parameter for parameter in library.parameters if parameter.id == parameter_id)


def test_encode_midi_target_message_program_change() -> None:
    parameter = _parameter("behringer_xtouch_mini", "select_layer_a")

    status, data = encode_midi_target_message(parameter, 0)

    assert status == 0xCA
    assert data == (0,)


def test_encode_midi_target_message_note_led() -> None:
    parameter = _parameter("behringer_xtouch_mini", "layer_a_top_button_1_led")

    status, data = encode_midi_target_message(parameter, 1)

    assert status == 0x9A
    assert data == (8, 127)


def test_encode_midi_target_message_note_led_off() -> None:
    parameter = _parameter("behringer_xtouch_mini", "layer_a_top_button_1_led")

    status, data = encode_midi_target_message(parameter, 0)

    assert status == 0x8A
    assert data == (8, 0)


def test_encode_midi_target_message_control_change_led_ring() -> None:
    parameter = _parameter("behringer_xtouch_mini", "layer_a_encoder_1_led_ring")

    status, data = encode_midi_target_message(parameter, 5)

    assert status == 0xBA
    assert data == (1, 5)


def test_resolve_midi_target_parameter_uses_adapter_library() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                }
            }
        }
    )

    parameter = resolve_midi_target_parameter(config, "xtouch_mini", "select_layer_b")
    minimum, maximum = lookup_midi_target_ranges(config, "xtouch_mini", "select_layer_b")

    assert parameter.label == "Select Layer B"
    assert minimum == 1
    assert maximum == 1


def test_encode_midi_target_message_rejects_sysex() -> None:
    library = get_midi_library("presonus_faderport")
    parameter = next(
        entry
        for entry in library.parameters
        if entry.id == "ch_1_lcd_track_name" and entry.direction == "target"
    )

    with pytest.raises(ValueError, match="sysex"):
        encode_midi_target_message(parameter, 0)
