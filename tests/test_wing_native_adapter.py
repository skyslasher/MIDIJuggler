import asyncio

import pytest

from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import MappedEvent, OscMessageEvent
from midijuggler.wing.native.client import WingNativeClient, WingPathBinding


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

            async def set_float(self, node_id: int, value: float) -> None:
                assert node_id == 99
                assert value == pytest.approx(0.25)
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
