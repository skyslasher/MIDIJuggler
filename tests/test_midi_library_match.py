from midijuggler.config import AdapterConfig
from midijuggler.midi.library_match import (
    build_source_index,
    resolve_incoming_controls,
    resolve_library_port,
)
from midijuggler.midi_library import get_midi_library


def test_xtouch_mini_matches_control_change_and_note() -> None:
    index = build_source_index(get_midi_library("behringer_xtouch_mini"))

    encoder_turn = index.match(0xB0, (1, 64))
    assert len(encoder_turn) == 1
    assert encoder_turn[0].control_id == "layer_a_encoder_1_turn"
    assert encoder_turn[0].value == 64.0

    fader = index.match(0xB0, (9, 100))
    assert len(fader) == 1
    assert fader[0].control_id == "layer_a_fader"
    assert fader[0].value == 100.0

    layer_b_fader = index.match(0xB0, (10, 55))
    assert len(layer_b_fader) == 1
    assert layer_b_fader[0].control_id == "layer_b_fader"

    layer_b_encoder = index.match(0xB0, (11, 42))
    assert len(layer_b_encoder) == 1
    assert layer_b_encoder[0].control_id == "layer_b_encoder_1_turn"
    assert layer_b_encoder[0].value == 42.0

    layer_b_encoder_8 = index.match(0xB0, (18, 3))
    assert len(layer_b_encoder_8) == 1
    assert layer_b_encoder_8[0].control_id == "layer_b_encoder_8_turn"

    button_press = index.match(0x90, (8, 127))
    assert len(button_press) == 1
    assert button_press[0].control_id == "layer_a_top_button_1"
    assert button_press[0].value == 127.0

    button_release = index.match(0x80, (8, 0))
    assert len(button_release) == 1
    assert button_release[0].control_id == "layer_a_top_button_1"
    assert button_release[0].value == 0.0


def test_faderport_port_filter_limits_pitch_bend_matches() -> None:
    library = get_midi_library("presonus_faderport")
    port_1 = build_source_index(library, "port_1")
    port_2 = build_source_index(library, "port_2")

    channel_1 = port_1.match(0xE0, (0, 64))
    channel_9 = port_2.match(0xE0, (0, 64))

    assert [match.control_id for match in channel_1] == ["ch_1_fader"]
    assert [match.control_id for match in channel_9] == ["ch_9_fader"]
    assert channel_1[0].value == 8192.0
    assert channel_9[0].value == 8192.0


def test_resolve_library_port_from_input_port_name() -> None:
    config = AdapterConfig(
        enabled=True,
        kind="midi",
        options={
            "input_port": "PreSonus FP16 Port 2",
            "midi_library": "presonus_faderport",
        },
    )

    assert resolve_library_port(config) == "port_2"


def test_unknown_message_returns_no_matches() -> None:
    index = build_source_index(get_midi_library("behringer_xtouch_mini"))

    assert index.match(0xF0, ()) == []


def test_relaxed_match_ignores_midi_channel_when_unique() -> None:
    index = build_source_index(get_midi_library("behringer_xtouch_mini"))

    matches = index.match_relaxed(0xB1, (1, 42))

    assert len(matches) == 1
    assert matches[0].control_id == "layer_a_encoder_1_turn"
    assert matches[0].value == 42.0


def test_resolve_incoming_controls_falls_back_to_raw_midi_id() -> None:
    matches = resolve_incoming_controls(None, 0xB0, (7, 100))

    assert len(matches) == 1
    assert matches[0].control_id == "cc_0_7"
    assert matches[0].value == 100.0
