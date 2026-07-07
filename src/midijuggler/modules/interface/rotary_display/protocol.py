"""Line protocol shared by USB-serial and documentation for OSC mapping."""

from __future__ import annotations

from dataclasses import dataclass

from midijuggler.clock import CLICK_INTERVALS
from midijuggler.events import MasterClockCommandEvent


@dataclass(frozen=True)
class RotarySyncState:
    bpm: float
    running: bool
    click_enabled: bool
    click_interval: str


def parse_serial_line(line: str) -> tuple[str, list[str]] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = stripped.split()
    return parts[0].lower(), parts[1:]


def serial_command_to_clock_event(
    command: str,
    args: list[str],
    *,
    source: str = "rotary_display",
) -> MasterClockCommandEvent | None:
    if command == "bpm" and args:
        return MasterClockCommandEvent(
            source=source,
            command="set_bpm",
            value=float(args[0]),
        )
    if command == "start_stop":
        return MasterClockCommandEvent(source=source, command="start_stop", value=1.0)
    if command == "click_toggle":
        return MasterClockCommandEvent(source=source, command="toggle_click", value=1.0)
    if command == "tap_tempo":
        return MasterClockCommandEvent(source=source, command="tap_tempo", value=1.0)
    if command == "interval" and args:
        interval = args[0].lower()
        if interval in CLICK_INTERVALS:
            return MasterClockCommandEvent(
                source=source,
                command="set_click_interval",
                value=interval,
            )
    return None


def format_sync_line(state: RotarySyncState) -> str:
    interval = state.click_interval if state.click_interval in CLICK_INTERVALS else "quarter"
    return (
        f"sync {state.bpm:.1f} "
        f"{1 if state.running else 0} "
        f"{1 if state.click_enabled else 0} "
        f"{interval}"
    )


def format_beat_line(value: float) -> str:
    return f"beat {value:.1f}"


def parse_hello_osc(arguments: tuple[object, ...]) -> tuple[str, int] | None:
    if len(arguments) < 2:
        return None
    host = str(arguments[0]).strip()
    try:
        port = int(arguments[1])
    except (TypeError, ValueError):
        return None
    if not host or port <= 0 or port > 65535:
        return None
    return host, port
