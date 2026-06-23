import asyncio

import pytest

from midijuggler.adapters.osc import OscAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, OscMessageEvent
from midijuggler.midi.echo_guard import OscEchoGuard


def test_osc_echo_guard_filters_matching_input_within_window() -> None:
    guard = OscEchoGuard(window_ms=30)
    guard.record("/ch/01/mix/fader", 0.5, now=100.0)

    assert guard.is_echo("/ch/01/mix/fader", 0.5, now=100.01) is True
    assert guard.is_echo("/ch/01/mix/fader", 0.50002, now=100.01) is True
    assert guard.is_echo("/ch/01/mix/fader", 0.52, now=100.01) is False
    assert guard.is_echo("/ch/01/mix/fader", 0.5, now=100.04) is False


def test_osc_adapter_ignores_recent_output_as_input(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> tuple[list[OscMessageEvent], list[ControlEvent]]:
        bus = EventBus()
        osc_events: list[OscMessageEvent] = []
        controls: list[ControlEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: osc_events.append(event))
        bus.subscribe(ControlEvent, lambda event: controls.append(event))

        adapter = OscAdapter(
            "x32",
            AdapterConfig(
                enabled=True,
                kind="osc",
                options={"echo_guard_ms": 30},
            ),
            bus,
        )
        adapter._configure_echo_guard()
        adapter._echo_guard.record("/ch/01/mix/fader", 0.5, now=10.0)

        monkeypatch.setattr(
            "midijuggler.adapters.osc.time.monotonic",
            lambda: 10.01,
        )
        await adapter._handle_input_messages(
            _encode_osc_datagram("/ch/01/mix/fader", 0.5)
        )

        monkeypatch.setattr(
            "midijuggler.adapters.osc.time.monotonic",
            lambda: 10.05,
        )
        await adapter._handle_input_messages(
            _encode_osc_datagram("/ch/01/mix/fader", 0.6)
        )

        return osc_events, controls

    osc_events, controls = asyncio.run(scenario())

    assert len(osc_events) == 2
    assert osc_events[0].echo_suppressed is True
    assert osc_events[1].echo_suppressed is False
    assert len(controls) == 1
    assert controls[0].control == "/ch/01/mix/fader"
    assert controls[0].value == pytest.approx(0.6)


def _encode_osc_datagram(address: str, value: float) -> bytes:
    from midijuggler.osc.protocol import encode_message

    return encode_message(address, [value])
