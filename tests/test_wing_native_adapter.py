import asyncio

import pytest

from midijuggler.adapters.wing_native import (
    _FEEDBACK_PUBLISH_INTERVAL_S,
    WingNativeAdapter,
)
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, MappedEvent, OscMessageEvent
from midijuggler.wing.native.client import WingNativeClient, WingPathBinding


def test_wing_native_start_marks_connected_without_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ImmediateClient(WingNativeClient):
        async def connect(self) -> None:
            return

        async def read_events(self) -> list[tuple[object, object]]:
            await asyncio.sleep(3600)
            return []

        async def close(self) -> None:
            return

    monkeypatch.setattr(
        "midijuggler.adapters.wing_native.WingNativeClient",
        ImmediateClient,
    )

    async def scenario() -> tuple[WingNativeAdapter, list[AdapterStatusEvent]]:
        bus = EventBus()
        status_events: list[AdapterStatusEvent] = []
        bus.subscribe(AdapterStatusEvent, lambda event: status_events.append(event))

        adapter = WingNativeAdapter(
            name="wing_native_foh",
            config=AdapterConfig(
                enabled=True,
                kind="wing_native",
                options={
                    "remote_host": "192.168.1.48",
                    "wing_library": "behringer_wing",
                },
            ),
            bus=bus,
        )
        await adapter.start()
        return adapter, status_events

    adapter, status_events = asyncio.run(scenario())

    try:
        assert adapter.running is True
        assert adapter._warmup_task is None  # noqa: SLF001
        assert adapter.connectivity_snapshot()["connection_phase"] == "connected"
        assert any(
            event.connection_phase == "connected"
            for event in status_events
        )
    finally:
        asyncio.run(adapter.stop())


def test_wing_native_adapter_publishes_input_updates() -> None:
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
        await adapter.stop()
        return events

    events = asyncio.run(scenario())

    assert len(events) == 1
    assert events[0].address == "/ch/1/fdr"
    assert events[0].direction == "input"
    assert events[0].arguments == (pytest.approx(0.5),)


def test_wing_native_adapter_send_resolves_path_and_records_output() -> None:
    async def scenario() -> tuple[list[bytes], OscMessageEvent | None]:
        bus = EventBus()
        output_events: list[OscMessageEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: output_events.append(event))

        sent: list[bytes] = []

        class FakeClient(WingNativeClient):
            async def resolve_path(self, path: str) -> int:
                assert path == "/ch/1/fdr"
                return 99

            async def set_float(
                self,
                node_id: int,
                value: float,
                *,
                raw: bool = False,
            ) -> None:
                assert node_id == 99
                assert value == pytest.approx(0.25)
                assert raw is True
                sent.append(b"sent")

        adapter = WingNativeAdapter(
            name="wing_native_foh",
            config=AdapterConfig(
                enabled=True,
                kind="wing_native",
                options={"remote_host": "192.168.1.48"},
            ),
            bus=bus,
        )
        adapter._client = FakeClient("192.168.1.48")  # noqa: SLF001
        adapter.running = True

        await adapter.send(
            MappedEvent(
                source="datapoint",
                target="wing_native_foh:/ch/1/fdr",
                value=0.25,
            )
        )
        output = next((event for event in output_events if event.direction == "output"), None)
        return sent, output

    sent, output = asyncio.run(scenario())

    assert sent == [b"sent"]
    assert output is not None
    assert output.address == "/ch/1/fdr"


def test_wing_native_adapter_send_uses_engineering_float_for_fader_db() -> None:
    async def scenario() -> bool:
        bus = EventBus()
        state = {"raw": False}

        class FakeClient(WingNativeClient):
            async def resolve_path(self, path: str) -> int:
                return 99

            async def set_float(
                self,
                node_id: int,
                value: float,
                *,
                raw: bool = False,
            ) -> None:
                assert value == pytest.approx(-5.873)
                state["raw"] = raw

        adapter = WingNativeAdapter(
            name="wing_native_foh",
            config=AdapterConfig(
                enabled=True,
                kind="wing_native",
                options={"remote_host": "192.168.1.48"},
            ),
            bus=bus,
        )
        adapter._client = FakeClient("192.168.1.48")  # noqa: SLF001
        adapter.running = True

        await adapter.send(
            MappedEvent(
                source="datapoint",
                target="wing_native_foh:/ch/1/fdr",
                value=-5.873,
            )
        )
        return state["raw"]

    assert asyncio.run(scenario()) is False
