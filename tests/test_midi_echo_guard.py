import asyncio

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, MidiMessageEvent
from midijuggler.midi.echo_guard import (
    DEFAULT_ECHO_GUARD_MS,
    MidiEchoGuard,
    parse_echo_guard_ms,
)


def test_parse_echo_guard_ms_defaults_and_bounds() -> None:
    assert parse_echo_guard_ms(None) == DEFAULT_ECHO_GUARD_MS
    assert parse_echo_guard_ms(0) == 0
    assert parse_echo_guard_ms(50) == 50
    with pytest.raises(ValueError, match=">= 0"):
        parse_echo_guard_ms(-1)
    with pytest.raises(ValueError, match="<= 5000"):
        parse_echo_guard_ms(5001)
    with pytest.raises(ValueError, match="integer"):
        parse_echo_guard_ms("fast")


def test_midi_echo_guard_filters_matching_input_within_window() -> None:
    guard = MidiEchoGuard(window_ms=30)
    guard.record(0xB0, (1, 64), now=100.0)

    assert guard.is_echo(0xB0, (1, 64), now=100.01) is True
    assert guard.is_echo(0xB0, (1, 65), now=100.01) is False
    assert guard.is_echo(0xB0, (1, 64), now=100.031) is False


def test_midi_echo_guard_disabled_when_window_zero() -> None:
    guard = MidiEchoGuard(window_ms=0)
    guard.record(0xB0, (1, 64), now=1.0)
    assert guard.is_echo(0xB0, (1, 64), now=1.0) is False


def test_midi_adapter_ignores_recent_output_as_input(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> tuple[list[ControlEvent], list[MidiMessageEvent]]:
        bus = EventBus()
        controls: list[ControlEvent] = []
        messages: list[MidiMessageEvent] = []
        bus.subscribe(ControlEvent, lambda event: controls.append(event))
        bus.subscribe(MidiMessageEvent, lambda event: messages.append(event))

        adapter = MidiAdapter(
            "xtouch_mini",
            AdapterConfig(
                enabled=True,
                kind="midi",
                options={
                    "midi_library": "behringer_xtouch_mini",
                    "echo_guard_ms": 30,
                },
            ),
            bus,
        )
        adapter.running = True
        adapter._source_index = adapter._load_source_index()
        adapter._configure_echo_guard()
        adapter._echo_guard.record(0xBA, (1, 42), now=10.0)

        monkeypatch.setattr(
            "midijuggler.adapters.midi.time.monotonic",
            lambda: 10.01,
        )
        await adapter._handle_input_message(0xBA, (1, 42))

        monkeypatch.setattr(
            "midijuggler.adapters.midi.time.monotonic",
            lambda: 10.05,
        )
        await adapter._handle_input_message(0xBA, (1, 43))

        return controls, messages

    controls, messages = asyncio.run(scenario())

    assert len(messages) == 1
    assert messages[0].direction == "input"
    assert len(controls) == 1
    assert controls[0].control == "layer_a_encoder_1_turn"
    assert controls[0].value == 43.0


def test_midi_adapter_uses_default_echo_guard_without_option() -> None:
    adapter = MidiAdapter(
        "midi",
        AdapterConfig(enabled=True, kind="midi", options={}),
        EventBus(),
    )
    adapter._configure_echo_guard()
    assert adapter._echo_guard.enabled is True
    assert adapter._echo_guard._window_seconds == pytest.approx(0.03)
