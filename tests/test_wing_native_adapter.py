import asyncio

import pytest

from midijuggler.adapters.wing_native import (
    _FADER_SEND_INTERVAL_S,
    _FEEDBACK_PUBLISH_INTERVAL_S,
    WingNativeAdapter,
)
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, MappedEvent, OscMessageEvent
from midijuggler.modules.modifier.range_map import db_to_fader_float
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
        await asyncio.sleep(_FADER_SEND_INTERVAL_S + 0.05)
        output = next((event for event in output_events if event.direction == "output"), None)
        return sent, output

    sent, output = asyncio.run(scenario())

    assert sent == [b"sent"]
    assert output is not None
    assert output.address == "/ch/1/fdr"


def test_wing_native_adapter_send_converts_fader_db_to_normalized_raw() -> None:
    async def scenario() -> tuple[float, bool]:
        bus = EventBus()
        state = {"value": 0.0, "raw": False}

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
                state["value"] = value
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
        await asyncio.sleep(_FADER_SEND_INTERVAL_S + 0.05)
        return state["value"], state["raw"]

    wire_value, raw = asyncio.run(scenario())

    assert wire_value == pytest.approx(db_to_fader_float(-5.873))
    assert raw is True


def test_wing_native_adapter_send_uses_engineering_db_when_range_registered() -> None:
    async def scenario() -> tuple[float, bool]:
        bus = EventBus()
        state = {"value": 0.0, "raw": True}

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
                state["value"] = value
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
        adapter.register_fader_output_range("/ch/1/fdr", -90.0, 10.0)

        await adapter.send(
            MappedEvent(
                source="datapoint",
                target="wing_native_foh:/ch/1/fdr",
                value=-5.873,
            )
        )
        await asyncio.sleep(_FADER_SEND_INTERVAL_S + 0.05)
        return state["value"], state["raw"]

    wire_value, raw = asyncio.run(scenario())

    assert wire_value == pytest.approx(-5.873)
    assert raw is False


def test_wing_native_adapter_send_small_positive_db_as_engineering_when_range_registered() -> None:
    async def scenario() -> tuple[float, bool]:
        bus = EventBus()
        state = {"value": 0.0, "raw": True}

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
                state["value"] = value
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
        adapter.register_fader_output_range("/ch/1/fdr", -90.0, 10.0)

        await adapter.send(
            MappedEvent(
                source="datapoint",
                target="wing_native_foh:/ch/1/fdr",
                value=0.476,
            )
        )
        await asyncio.sleep(_FADER_SEND_INTERVAL_S + 0.05)
        return state["value"], state["raw"]

    wire_value, raw = asyncio.run(scenario())

    assert wire_value == pytest.approx(0.476)
    assert raw is False
    assert wire_value != pytest.approx(db_to_fader_float(0.476))


def test_wing_native_adapter_converts_engineering_feedback_to_db() -> None:
    async def scenario() -> OscMessageEvent | None:
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
        adapter.register_fader_output_range("/ch/1/fdr", -90.0, 10.0)

        from midijuggler.wing.native.decoder import WingNodeData

        wire = db_to_fader_float(0.476)
        await adapter._publish_node_data(  # noqa: SLF001
            WingNodeData(99, float_value=wire, float_raw=True)
        )
        await asyncio.sleep(_FEEDBACK_PUBLISH_INTERVAL_S + 0.05)
        await adapter.stop()
        return next((event for event in events if event.direction == "input"), None)

    event = asyncio.run(scenario())

    assert event is not None
    assert event.arguments == (pytest.approx(0.476, abs=0.05),)


def test_wing_native_adapter_coalesces_rapid_fader_sends() -> None:
    async def scenario() -> tuple[int, float | None]:
        bus = EventBus()
        sent: list[float] = []

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
                sent.append(value)

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
        adapter.register_fader_output_range("/ch/1/fdr", -90.0, 10.0)

        for value in (-1.0, 0.0, 0.476, 2.0):
            await adapter.send(
                MappedEvent(
                    source="datapoint",
                    target="wing_native_foh:/ch/1/fdr",
                    value=value,
                )
            )
        await asyncio.sleep(_FADER_SEND_INTERVAL_S + 0.05)
        await adapter.stop()
        return len(sent), sent[-1] if sent else None

    count, last = asyncio.run(scenario())

    assert count == 1
    assert last == pytest.approx(2.0)
