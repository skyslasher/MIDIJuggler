import asyncio

import pytest

from midijuggler.adapters.wing_native import (
    _FEEDBACK_PUBLISH_INTERVAL_S,
    WingNativeAdapter,
)
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent
from midijuggler.wing.native.client import WingNativeClient, WingPathBinding
from midijuggler.wing.native.connectivity import WingNativeConnectivity


def test_wing_native_connectivity_snapshot_reports_feedback_age() -> None:
    connectivity = WingNativeConnectivity()
    connectivity.note_connected("192.168.1.48", 2222)
    connectivity.note_feedback("/ch/1/fdr", 0.5)
    connectivity.paths_cached = 12

    snapshot = connectivity.as_dict()

    assert snapshot["connected"] is True
    assert snapshot["connection_phase"] == "connected"
    assert snapshot["last_feedback_path"] == "/ch/1/fdr"
    assert snapshot["last_feedback_value"] == pytest.approx(0.5)
    assert snapshot["last_feedback_age_s"] is not None
    assert snapshot["paths_cached"] == 12


def test_wing_native_adapter_notes_feedback_without_status_publish() -> None:
    async def scenario() -> tuple[WingNativeAdapter, list[AdapterStatusEvent]]:
        bus = EventBus()
        events: list[AdapterStatusEvent] = []
        bus.subscribe(AdapterStatusEvent, lambda event: events.append(event))

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
        adapter._connectivity.note_connected("192.168.1.48", 2222)  # noqa: SLF001
        adapter.running = True

        from midijuggler.wing.native.decoder import WingNodeData

        await adapter._publish_node_data(WingNodeData(99, float_value=0.5))  # noqa: SLF001
        await asyncio.sleep(_FEEDBACK_PUBLISH_INTERVAL_S + 0.05)
        return adapter, events

    adapter, events = asyncio.run(scenario())

    try:
        assert events == []
        snapshot = adapter.connectivity_snapshot()
        assert snapshot["last_feedback_path"] == "/ch/1/fdr"
        assert snapshot["last_feedback_value"] == pytest.approx(0.5)
    finally:
        adapter.running = False
        for task in list(adapter._fader_flush_tasks.values()):  # noqa: SLF001
            task.cancel()
