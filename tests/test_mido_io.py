from types import SimpleNamespace

from midijuggler.midi.mido_io import (
    _infer_config_port_id,
    mido_message_to_status_data,
)


def test_mido_message_to_status_data_control_change() -> None:
    message = SimpleNamespace(type="control_change", bytes=lambda: [0xB0, 7, 64])
    assert mido_message_to_status_data(message) == (0xB0, (7, 64))


def test_mido_message_to_status_data_clock() -> None:
    message = SimpleNamespace(type="clock", bytes=lambda: [0xF8])
    assert mido_message_to_status_data(message) == (0xF8, ())


def test_infer_config_port_id_extracts_port_suffix() -> None:
    assert _infer_config_port_id("X-TOUCH MINI MIDI 1") == "X-TOUCH MINI MIDI 1"
    assert (
        _infer_config_port_id("X-TOUCH MINI X-TOUCH MINI")
        == "X-TOUCH MINI"
    )
