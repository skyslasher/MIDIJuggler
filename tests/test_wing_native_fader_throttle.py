"""Tests for Wing Native fader feedback throttling."""

import asyncio

import pytest

from midijuggler.adapters.wing_native import (
    _FADER_FEEDBACK_DEADBAND,
    _FEEDBACK_PUBLISH_INTERVAL_S,
    WingNativeAdapter,
)
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import OscMessageEvent
from midijuggler.wing.native.client import WingNativeClient, WingPathBinding


def test_wing_native_coalesces_fader_feedback() -> None:
    async def scenario() -> list[OscMessageEvent]:
        bus = EventBus()
        events: list[OscMessageEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: events.append(event))

        adapter = WingNativeAdapter(
            name="wing_native_foh",
            config=AdapterConfig(
                enabled=True,
                kind="wing_native",
                options={"remote_host": "192.168.1.48"},
            ),
            bus=bus,
        )
        adapter._client = WingNativeClient("192.168.1.48")  # noqa: SLF001
        adapter._client.remember_binding(WingPathBinding("/ch/1/fdr", 99))  # noqa: SLF001
        adapter.running = True

        from midijuggler.wing.native.decoder import WingNodeData

        for value in (0.0, 0.005, 0.01, 0.015, 0.02):
            await adapter._publish_node_data(WingNodeData(99, float_value=value))  # noqa: SLF001
        await asyncio.sleep(_FEEDBACK_PUBLISH_INTERVAL_S + 0.05)
        await adapter.stop()
        return events

    events = asyncio.run(scenario())
    assert len(events) == 1
    assert events[0].arguments == (pytest.approx(0.02),)


def test_wing_native_fader_deadband_skips_unchanged_flush() -> None:
    async def scenario() -> list[OscMessageEvent]:
        bus = EventBus()
        events: list[OscMessageEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: events.append(event))

        adapter = WingNativeAdapter(
            name="wing_native_foh",
            config=AdapterConfig(
                enabled=True,
                kind="wing_native",
                options={"remote_host": "192.168.1.48"},
            ),
            bus=bus,
        )
        adapter._client = WingNativeClient("192.168.1.48")  # noqa: SLF001
        adapter._client.remember_binding(WingPathBinding("/ch/1/fdr", 99))  # noqa: SLF001
        adapter.running = True

        from midijuggler.wing.native.decoder import WingNodeData

        await adapter._publish_node_data(WingNodeData(99, float_value=0.5))  # noqa: SLF001
        await asyncio.sleep(_FEEDBACK_PUBLISH_INTERVAL_S + 0.05)
        for offset in (0.001, 0.002, 0.003):
            await adapter._publish_node_data(  # noqa: SLF001
                WingNodeData(99, float_value=0.5 + offset)
            )
        await asyncio.sleep(_FEEDBACK_PUBLISH_INTERVAL_S + 0.05)
        await adapter.stop()
        return events

    events = asyncio.run(scenario())
    assert len(events) == 1
    assert events[0].arguments == (pytest.approx(0.5),)
    assert _FADER_FEEDBACK_DEADBAND >= 0.01
