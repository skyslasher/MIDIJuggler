import pytest

from midijuggler.events import OscMessageEvent
from midijuggler.master_clock import MasterClockRemote
from midijuggler.config import MasterClockConfig
from midijuggler.modules.interface.rotary_display.protocol import (
    RotarySyncState,
    format_beat_line,
    format_sync_line,
    parse_hello_osc,
    parse_serial_line,
    serial_command_to_clock_event,
)


def test_master_clock_remote_maps_start_stop_without_arguments() -> None:
    remote = MasterClockRemote(MasterClockConfig())
    event = OscMessageEvent(
        source="osc",
        address="/midijuggler/clock/start_stop",
        arguments=(),
        direction="input",
    )
    command = remote.command_from_osc(event)
    assert command is not None
    assert command.command == "start_stop"


def test_master_clock_remote_maps_click_toggle_without_arguments() -> None:
    remote = MasterClockRemote(MasterClockConfig())
    event = OscMessageEvent(
        source="osc",
        address="/midijuggler/clock/click_toggle",
        arguments=(),
        direction="input",
    )
    command = remote.command_from_osc(event)
    assert command is not None
    assert command.command == "toggle_click"


def test_serial_command_mapping() -> None:
    event = serial_command_to_clock_event("bpm", ["128.5"])
    assert event is not None
    assert event.command == "set_bpm"
    assert event.value == pytest.approx(128.5)

    event = serial_command_to_clock_event("interval", ["half"])
    assert event is not None
    assert event.command == "set_click_interval"
    assert event.value == "half"

    event = serial_command_to_clock_event("tap_tempo", [])
    assert event is not None
    assert event.command == "tap_tempo"


def test_serial_sync_and_beat_lines() -> None:
    line = format_sync_line(
        RotarySyncState(bpm=120.0, running=True, click_enabled=False, click_interval="quarter")
    )
    assert line == "sync 120.0 1 0 quarter"
    assert format_beat_line(1.0) == "beat 1.0"


def test_parse_serial_line_ignores_comments() -> None:
    assert parse_serial_line("# comment") is None
    assert parse_serial_line("start_stop") == ("start_stop", [])


def test_parse_hello_osc() -> None:
    assert parse_hello_osc(("192.168.1.50", 9001)) == ("192.168.1.50", 9001)
    assert parse_hello_osc(("bad", "nope")) is None
