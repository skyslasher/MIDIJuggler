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
    assert parameters["bus_16_fader"].address == "/bus/16/mix/fader"
    assert parameters["main_st_fader"].value_max == 1.0
    assert len(library.parameters) == 178


def test_wing_library_expands_common_templates() -> None:
    library = get_osc_library("behringer_wing")
    parameters = {parameter.id: parameter for parameter in library.parameters}

    assert parameters["ch_1_fdr"].address == "/ch/1/fdr"
    assert parameters["ch_48_mute"].address == "/ch/48/mute"
    assert parameters["dca_16_fdr"].address == "/dca/16/fdr"
    assert parameters["main_1_mute"].value_type == "int"
    assert len(library.parameters) == 228


def test_unknown_library_raises_key_error() -> None:
    try:
        get_osc_library("unknown")
    except KeyError as exc:
        assert "unknown OSC library" in str(exc)
    else:
        raise AssertionError("expected KeyError")
