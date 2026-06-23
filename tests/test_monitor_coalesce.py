"""Tests for monitor WebSocket coalescing."""

import asyncio

import pytest

from midijuggler.events import ControlEvent, MidiMessageEvent, OscMessageEvent
from midijuggler.web.monitor_coalesce import (
    MonitorCoalescer,
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
