"""Tests for monitor WebSocket coalescing."""

import asyncio

import pytest

from midijuggler.events import ControlEvent, LogEvent, MidiMessageEvent, OscMessageEvent
from midijuggler.web.monitor_coalesce import (
    MonitorCoalescer,
    MonitorEventFilter,
    monitor_datapoint_key,
    monitor_event_key,
)


def test_monitor_event_key_matches_wing_fader_osc() -> None:
    event = OscMessageEvent(
        source="wing_native_foh",
        address="/ch/1/fdr",
        arguments=(0.5,),
        direction="input",
        canonical_address="/ch/1/fdr",
    )
    assert monitor_event_key(event) == "osc:wing_native_foh:/ch/1/fdr"


def test_monitor_event_key_ignores_non_fader_control() -> None:
    event = ControlEvent(source="gpio", control="pin17", value=1.0)
    assert monitor_event_key(event) is None


def test_monitor_datapoint_key_matches_fader_point() -> None:
    assert (
        monitor_datapoint_key(
            {
                "id": "xtouch_mini.layer_a_fader",
                "value_type": "float",
                "float_value": 64.0,
            }
        )
        == "datapoint:xtouch_mini.layer_a_fader"
    )


def test_monitor_coalescer_flushes_latest_payload() -> None:
    async def scenario() -> list[dict[str, object]]:
        coalescer = MonitorCoalescer(interval_s=0.05)
        sent: list[dict[str, object]] = []

        async def capture(payload: dict[str, object]) -> None:
            sent.append(payload)

        await coalescer.offer("osc:wing:/ch/1/fdr", {"value": 0.1}, capture)
        await coalescer.offer("osc:wing:/ch/1/fdr", {"value": 0.2}, capture)
        await coalescer.offer("osc:wing:/ch/1/fdr", {"value": 0.3}, capture)
        await asyncio.sleep(0.12)
        await coalescer.close()
        return sent

    sent = asyncio.run(scenario())
    assert sent == [{"value": 0.3}]


def test_monitor_coalescer_immediate_bypasses_delay() -> None:
    async def scenario() -> list[dict[str, object]]:
        coalescer = MonitorCoalescer(interval_s=0.2)
        sent: list[dict[str, object]] = []

        async def capture(payload: dict[str, object]) -> None:
            sent.append(payload)

        await coalescer.offer(
            "osc:wing:/ch/1/fdr",
            {"value": 0.5},
            capture,
            immediate=True,
        )
        await coalescer.close()
        return sent

    sent = asyncio.run(scenario())
    assert sent == [{"value": 0.5}]


def test_monitor_event_filter_suppresses_repeat_rotary_hello() -> None:
    event_filter = MonitorEventFilter()
    hello = OscMessageEvent(
        source="osc",
        address="/midijuggler/rotary/hello",
        arguments=("rotary-267248.local", 9001),
        direction="input",
    )

    assert event_filter.suppress(hello) is False
    assert event_filter.suppress(hello) is True
    assert event_filter.suppress(hello.as_dict()) is True

    changed = OscMessageEvent(
        source="osc",
        address="/midijuggler/rotary/hello",
        arguments=("rotary-stage.local", 9001),
        direction="input",
    )
    assert event_filter.suppress(changed) is False


def test_monitor_event_filter_suppresses_rotary_hello_control_event() -> None:
    """OSC adapter mirrors hello port as ControlEvent (= 9001 in monitor)."""
    event_filter = MonitorEventFilter()
    control = ControlEvent(
        source="osc",
        control="/midijuggler/rotary/hello",
        value=9001.0,
    )

    assert event_filter.suppress(control) is True
    assert event_filter.suppress(control.as_dict()) is True


def test_monitor_event_filter_normalizes_hello_port_type() -> None:
    event_filter = MonitorEventFilter()
    hello_int = OscMessageEvent(
        source="osc",
        address="/midijuggler/rotary/hello",
        arguments=("rotary-267248.local", 9001),
        direction="input",
    )
    hello_float = OscMessageEvent(
        source="osc",
        address="/midijuggler/rotary/hello",
        arguments=("rotary-267248.local", 9001.0),
        direction="input",
    )

    assert event_filter.suppress(hello_int) is False
    assert event_filter.suppress(hello_float) is True


def test_monitor_event_filter_suppresses_repeat_registration_logs() -> None:
    event_filter = MonitorEventFilter()
    registered = LogEvent(
        source="log",
        level="INFO",
        message="rotary display registered at rotary-267248.local:9001",
        logger="midijuggler.modules.interface.rotary_display.module",
    )
    re_registered = LogEvent(
        source="log",
        level="DEBUG",
        message="rotary display re-registered at rotary-267248.local:9001",
        logger="midijuggler.modules.interface.rotary_display.module",
    )

    assert event_filter.suppress(registered) is False
    assert event_filter.suppress(registered) is True
    assert event_filter.suppress(re_registered) is True
    assert event_filter.suppress(registered.as_dict()) is True
