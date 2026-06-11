from midijuggler.midi.alsa import parse_aseqdump_line
from midijuggler.system_info import (
    parse_aconnect_ports,
    resolve_midi_input_port_address,
    resolve_midi_output_port_address,
    resolve_midi_port_address,
)


def test_parse_aseqdump_line_note_on() -> None:
    assert parse_aseqdump_line(" 24:0   Note on                 0, note 60, velocity 127") == (
        0x90,
        (60, 127),
    )


def test_parse_aseqdump_line_control_change() -> None:
    assert parse_aseqdump_line(
        " 24:0   Control change          0, controller 7, value 100"
    ) == (0xB0, (7, 100))


def test_parse_aseqdump_line_clock() -> None:
    assert parse_aseqdump_line(" 24:0   Clock") == (0xF8, ())


def test_parse_aconnect_ports_includes_address() -> None:
    ports = parse_aconnect_ports(
        """
        client 24: 'X-TOUCHMINI' [type=kernel]
            0 'X-TOUCH MINI'
        """
    )

    assert ports == [
        {
            "id": "X-TOUCH MINI",
            "address": "24:0",
            "label": "X-TOUCHMINI / X-TOUCH MINI (24:0)",
            "client": "X-TOUCHMINI",
        }
    ]


def test_resolve_midi_port_addresses_use_readable_and_writable_lists(monkeypatch) -> None:
    monkeypatch.setattr(
        "midijuggler.system_info.list_midi_input_ports",
        lambda: parse_aconnect_ports(
            """
            client 24: 'X-TOUCHMINI' [type=kernel]
                0 'X-TOUCH MINI'
            """
        ),
    )
    monkeypatch.setattr(
        "midijuggler.system_info.list_midi_output_ports",
        lambda: parse_aconnect_ports(
            """
            client 24: 'X-TOUCHMINI' [type=kernel]
                1 'X-TOUCH MINI'
            """
        ),
    )

    assert resolve_midi_input_port_address("X-TOUCH MINI") == "24:0"
    assert resolve_midi_output_port_address("X-TOUCH MINI") == "24:1"
    assert resolve_midi_port_address("X-TOUCH MINI") == "24:1"
    assert resolve_midi_input_port_address("missing") is None
