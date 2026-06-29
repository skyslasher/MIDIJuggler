from midijuggler.midi_library import get_midi_library, list_midi_libraries


def test_lists_packaged_midi_libraries() -> None:
    libraries = list_midi_libraries()

    assert [library.id for library in libraries] == [
        "behringer_wing",
        "behringer_xtouch_mini",
        "presonus_faderport",
    ]


def test_xtouch_mini_library_contains_layers_controls_and_feedback() -> None:
    library = get_midi_library("behringer_xtouch_mini")
    parameters = {parameter.id: parameter for parameter in library.parameters}

    assert parameters["layer_a_encoder_1_turn"].message_type == "control_change"
    assert parameters["layer_a_encoder_1_turn"].midi_channel == 11
    assert parameters["layer_a_encoder_1_turn"].number == 1
    assert parameters["layer_b_encoder_8_turn"].number == 18
    assert parameters["layer_a_encoder_1_push"].number == 0
    assert parameters["layer_b_encoder_8_push"].number == 31
    assert parameters["layer_a_top_button_1"].number == 8
    assert parameters["layer_b_bottom_button_8"].number == 47
    assert parameters["layer_a_fader"].number == 9
    assert parameters["layer_b_fader"].number == 10

    assert parameters["layer_a_encoder_8_led_ring"].direction == "target"
    assert parameters["layer_a_encoder_8_led_ring"].number == 8
    assert parameters["layer_a_encoder_8_led_ring"].midi_channel == 12
    assert parameters["layer_a_encoder_8_led_ring"].value_max == 28
    assert parameters["layer_a_encoder_1_value"].midi_channel == 11
    assert parameters["layer_a_encoder_1_value"].number == 1
    assert parameters["layer_a_encoder_1_value"].value_max == 127
    assert parameters["layer_b_encoder_8_led_ring"].number == 18
    assert parameters["layer_b_encoder_8_value"].number == 18
    assert parameters["layer_a_top_button_1_led"].number == 8
    assert parameters["layer_a_top_button_1_led"].value_max == 1
    assert parameters["layer_a_top_button_1_led"].note_on_velocity == 127
    assert parameters["layer_a_top_button_1_led"].note_off_velocity == 0
    assert parameters["layer_b_bottom_button_8_led"].number == 47
    assert parameters["select_layer_b"].message_type == "program_change"
    assert parameters["set_mc_mode"].number == 127
    assert len(library.parameters) == 134


def test_faderport_library_contains_channel_controls_and_lcd_track_names() -> None:
    library = get_midi_library("presonus_faderport")
    parameters = {parameter.id: parameter for parameter in library.parameters}

    assert parameters["ch_1_fader"].message_type == "pitch_bend"
    assert parameters["ch_1_fader"].port == "port_1"
    assert parameters["ch_1_fader"].midi_channel == 1
    assert parameters["ch_8_select"].number == 31
    assert parameters["ch_9_fader"].port == "port_2"
    assert parameters["ch_9_fader"].midi_channel == 1
    assert parameters["ch_16_mute"].number == 23

    lcd = parameters["ch_16_lcd_track_name"]
    assert lcd.message_type == "sysex"
    assert lcd.value_type == "text"
    assert lcd.port == "port_2"
    assert lcd.strip == 7
    assert lcd.line == 0
    assert lcd.text_length == 7
    assert lcd.sysex_template == "F0 00 01 06 02 12 07 00 00 {text} F7"

    assert len(library.parameters) == 118


def test_wing_midi_library_uses_official_port4_cc_mapping() -> None:
    library = get_midi_library("behringer_wing")
    parameters = {parameter.id: parameter for parameter in library.parameters}

    assert parameters["ch_1_fdr"].midi_channel == 1
    assert parameters["ch_1_fdr"].number == 12
    assert parameters["ch_21_fdr"].number == 44
    assert parameters["ch_1_mute"].midi_channel == 2
    assert parameters["ch_1_pan"].midi_channel == 3
    assert parameters["bus_1_fdr"].number == 78
    assert parameters["dca_16_fdr"].midi_channel == 4
    assert parameters["dca_16_fdr"].number == 27
    assert parameters["mute_group_5_mute"].number == 44
    assert parameters["fx_1_insert_on"].midi_channel == 9
    assert parameters["fx_1_insert_on"].number == 12
    assert parameters["fx_9_insert_on"].midi_channel == 9
    assert parameters["fx_9_insert_on"].number == 70
    assert parameters["fx_1_param_17"].number == 31
    assert parameters["fx_9_param_24"].number == 102
    assert len(library.parameters) == 824


def test_faderport_library_contains_transport_controls() -> None:
    parameters = {
        parameter.id: parameter
        for parameter in get_midi_library("presonus_faderport").parameters
    }

    assert parameters["transport_play"].number == 94
    assert parameters["transport_record"].number == 95
    assert parameters["transport_loop"].number == 86


def test_unknown_midi_library_raises_key_error() -> None:
    try:
        get_midi_library("unknown")
    except KeyError as exc:
        assert "unknown MIDI library" in str(exc)
    else:
        raise AssertionError("expected KeyError")
