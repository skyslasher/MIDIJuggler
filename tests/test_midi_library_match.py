from midijuggler.config import AdapterConfig
from midijuggler.midi.library_match import (
    build_source_index,
    resolve_incoming_controls,
    resolve_library_port,
)
from midijuggler.midi_library import get_midi_library


XT_CHANNEL = 0x0A
XT_CC = 0xB0 | XT_CHANNEL
XT_NOTE_ON = 0x90 | XT_CHANNEL
XT_NOTE_OFF = 0x80 | XT_CHANNEL


def test_xtouch_mini_matches_control_change_and_note() -> None:
    index = build_source_index(get_midi_library("behringer_xtouch_mini"))

    encoder_turn = index.match(XT_CC, (1, 64))
    assert len(encoder_turn) == 1
    assert encoder_turn[0].control_id == "layer_a_encoder_1_turn"
    assert encoder_turn[0].value == 64.0

    fader = index.match(XT_CC, (9, 100))
    assert len(fader) == 1
    assert fader[0].control_id == "layer_a_fader"
    assert fader[0].value == 100.0

    layer_b_fader = index.match(XT_CC, (10, 55))
    assert len(layer_b_fader) == 1
    assert layer_b_fader[0].control_id == "layer_b_fader"

    layer_b_encoder = index.match(XT_CC, (11, 42))
    assert len(layer_b_encoder) == 1
    assert layer_b_encoder[0].control_id == "layer_b_encoder_1_turn"
    assert layer_b_encoder[0].value == 42.0

    layer_b_encoder_8 = index.match(XT_CC, (18, 3))
    assert len(layer_b_encoder_8) == 1
    assert layer_b_encoder_8[0].control_id == "layer_b_encoder_8_turn"

    button_press = index.match(XT_NOTE_ON, (8, 127))
    assert len(button_press) == 1
    assert button_press[0].control_id == "layer_a_top_button_1"
    assert button_press[0].value == 127.0

    button_release = index.match(XT_NOTE_OFF, (8, 0))
    assert len(button_release) == 1
    assert button_release[0].control_id == "layer_a_top_button_1"
    assert button_release[0].value == 0.0


def test_xtouch_mini_matches_program_change() -> None:
    index = build_source_index(get_midi_library("behringer_xtouch_mini"))

    assert index.match(0xC0 | 10, (0,)) == []
    assert index.match(0xC0 | 10, (1,)) == []


def test_format_raw_midi_control_program_change() -> None:
    from midijuggler.midi.library_match import extract_midi_value, format_raw_midi_control

    assert format_raw_midi_control(0xCA, (1,)) == "program_10_1"
    assert extract_midi_value(0xCA, (1,)) == 1.0


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

    matches = index.match_relaxed(0xBB, (1, 42))

    assert len(matches) == 1
    assert matches[0].control_id == "layer_a_encoder_1_turn"
    assert matches[0].value == 42.0


def test_resolve_incoming_controls_falls_back_to_raw_midi_id() -> None:
    matches = resolve_incoming_controls(None, 0xB0, (7, 100))

    assert len(matches) == 1
    assert matches[0].control_id == "cc_0_7"
    assert matches[0].value == 100.0
