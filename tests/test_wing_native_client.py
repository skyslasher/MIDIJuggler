import asyncio
import contextlib

import pytest

from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import MappedEvent
from midijuggler.wing.native.client import (
    LIST_CHILDREN_DRAIN_TIMEOUT_SECONDS,
    LIST_CHILDREN_TIMEOUT_SECONDS,
    WingNativeClient,
    _find_child,
)
from midijuggler.wing.native.decoder import WingDecodeKind, WingNodeDef
from midijuggler.wing.native.protocol import encode_keepalive, encode_request_node_definition


def _node_def(*, node_id: int, name: str, parent_id: int = 0) -> WingNodeDef:
    return WingNodeDef(
        node_id=node_id,
        parent_id=parent_id,
        index=0,
        name=name,
        long_name=name,
        flags=0x0030,
    )


class _MockWriter:
    def __init__(self) -> None:
        self.closing = False

    def write(self, _payload: bytes) -> None:
        return

    async def drain(self) -> None:
        return

    def close(self) -> None:
        self.closing = True

    async def wait_closed(self) -> None:
        return


@pytest.fixture
def short_list_children_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "midijuggler.wing.native.client.LIST_CHILDREN_TIMEOUT_SECONDS",
        0.05,
    )
    monkeypatch.setattr(
        "midijuggler.wing.native.client.LIST_CHILDREN_DRAIN_TIMEOUT_SECONDS",
        0.5,
    )


def test_find_child_filters_by_parent_and_supports_dollar_prefix() -> None:
    ch = _node_def(node_id=10, name="ch", parent_id=0)
    channel = _node_def(node_id=11, name="1", parent_id=10)
    fdr = _node_def(node_id=12, name="$fdr", parent_id=11)
    other_one = _node_def(node_id=99, name="1", parent_id=0)
    children = [ch, channel, fdr, other_one]

    assert _find_child(children, "ch", 0) == ch
    assert _find_child(children, "1", 10) == channel
    assert _find_child(children, "fdr", 11) == fdr


def test_list_children_drains_stale_response_before_next_request(
    short_list_children_timeouts: None,
) -> None:
    async def scenario() -> list[WingNodeDef]:
        client = WingNativeClient("127.0.0.1")
        client._writer = _MockWriter()  # noqa: SLF001

        writes: list[bytes] = []

        async def capture_write(payload: bytes) -> None:
            writes.append(payload)

        client._write_payload = capture_write  # type: ignore[method-assign]  # noqa: SLF001

        timed_out = asyncio.create_task(client.list_children(0))
        with pytest.raises(TimeoutError):
            await timed_out

        assert encode_keepalive() in writes
        assert encode_request_node_definition(0) in writes

        stale = [
            (WingDecodeKind.NODE_DEF, _node_def(node_id=99, name="stale")),
            (WingDecodeKind.REQUEST_END, None),
        ]
        client.handle_events(stale)

        resolved = asyncio.create_task(client.list_children(0))
        await asyncio.sleep(0)
        assert not resolved.done()

        fresh = [
            (WingDecodeKind.NODE_DEF, _node_def(node_id=42, name="ch")),
            (WingDecodeKind.REQUEST_END, None),
        ]
        client.handle_events(fresh)
        return await resolved

    children = asyncio.run(scenario())

    assert len(children) == 1
    assert children[0].node_id == 42
    assert children[0].name == "ch"


def test_concurrent_warmup_and_send_both_complete(
    short_list_children_timeouts: None,
) -> None:
    async def scenario() -> int:
        client = WingNativeClient("127.0.0.1")
        client._writer = _MockWriter()  # noqa: SLF001

        requested_nodes: asyncio.Queue[int] = asyncio.Queue()
        resolve_responses = {
            0: _node_def(node_id=10, name="ch", parent_id=0),
            10: _node_def(node_id=11, name="1", parent_id=10),
            11: _node_def(node_id=12, name="$fdr", parent_id=11),
        }

        async def capture_write(payload: bytes) -> None:
            if payload == encode_request_node_definition(0):
                await requested_nodes.put(0)
                return
            marker = bytes([0xD7])
            if marker in payload:
                offset = payload.index(marker) + 1
                node_id = int.from_bytes(payload[offset : offset + 4], "big", signed=True)
                await requested_nodes.put(node_id)

        client._write_payload = capture_write  # type: ignore[method-assign]  # noqa: SLF001

        async def auto_responder() -> None:
            while True:
                node_id = await requested_nodes.get()
                while True:
                    pending = client._pending_node_defs  # noqa: SLF001
                    if pending is not None and not pending.future.done():
                        break
                    await asyncio.sleep(0.001)
                response = resolve_responses.get(
                    node_id,
                    _node_def(node_id=1, name="warm"),
                )
                client.handle_events(
                    [
                        (WingDecodeKind.NODE_DEF, response),
                        (WingDecodeKind.REQUEST_END, None),
                    ]
                )

        responder = asyncio.create_task(auto_responder())

        async def warmup() -> None:
            for _ in range(5):
                await client.list_children(0)

        async def send_resolve() -> int:
            return await client.resolve_path("/ch/1/fdr")

        warmup_task = asyncio.create_task(warmup())
        send_task = asyncio.create_task(send_resolve())
        node_id = await send_task
        await warmup_task
        responder.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await responder
        return node_id

    node_id = asyncio.run(scenario())

    assert node_id == 12


def test_wing_native_send_handles_resolve_timeout_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[list[bytes], bool]:
        bus = EventBus()
        sent: list[bytes] = []
        crashed = False

        class TimeoutClient(WingNativeClient):
            async def resolve_path(self, path: str) -> int:
                assert path == "/ch/1/fdr"
                raise TimeoutError("list_children timed out")

            async def set_float(self, node_id: int, value: float) -> None:
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
        adapter._client = TimeoutClient("192.168.1.48")  # noqa: SLF001
        adapter.running = True

        try:
            await adapter.send(
                MappedEvent(
                    source="datapoint",
                    target="wing_native_foh:/ch/1/fdr",
                    value=0.25,
                )
            )
        except Exception:
            crashed = True
        return sent, crashed

    sent, crashed = asyncio.run(scenario())

    assert crashed is False
    assert sent == []
