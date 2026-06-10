from midijuggler.osc_library import get_osc_library, list_osc_libraries


def test_lists_packaged_behringer_osc_libraries() -> None:
    libraries = list_osc_libraries()

    assert [library.id for library in libraries] == [
        "behringer_wing",
        "behringer_x32",
    ]


def test_x32_library_expands_common_templates() -> None:
    library = get_osc_library("behringer_x32")
    parameters = {parameter.id: parameter for parameter in library.parameters}

    assert parameters["ch_01_fader"].address == "/ch/01/mix/fader"
    assert parameters["ch_32_on"].address == "/ch/32/mix/on"
    assert parameters["ch_01_bus_01_send"].address == "/ch/01/mix/01/level"
    assert parameters["ch_32_bus_16_send"].address == "/ch/32/mix/16/level"
    assert parameters["ch_32_bus_16_send"].category == "send"
    assert parameters["bus_16_fader"].address == "/bus/16/mix/fader"
    assert parameters["main_st_fader"].value_max == 1.0
    assert len(library.parameters) == 658


def test_wing_library_expands_common_templates() -> None:
    library = get_osc_library("behringer_wing")
    parameters = {parameter.id: parameter for parameter in library.parameters}

    assert parameters["ch_1_fdr"].address == "/ch/1/fdr"
    assert parameters["ch_48_mute"].address == "/ch/48/mute"
    assert parameters["ch_1_bus_1_send"].address == "/ch/1/send/1/lvl"
    assert parameters["ch_48_bus_16_send"].address == "/ch/48/send/16/lvl"
    assert parameters["ch_48_bus_16_send"].category == "send"
    assert parameters["dca_16_fdr"].address == "/dca/16/fdr"
    assert parameters["main_1_mute"].value_type == "int"
    assert len(library.parameters) == 996


def test_unknown_library_raises_key_error() -> None:
    try:
        get_osc_library("unknown")
    except KeyError as exc:
        assert "unknown OSC library" in str(exc)
    else:
        raise AssertionError("expected KeyError")
