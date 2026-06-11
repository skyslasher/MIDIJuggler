import asyncio
import socket
from typing import Any

import pytest

from midijuggler.adapters.osc import OscAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, MappedEvent, OscMessageEvent
from midijuggler.osc.protocol import decode_messages, encode_message


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_osc_adapter_publishes_input_messages_and_controls() -> None:
    async def scenario() -> tuple[list[OscMessageEvent], list[ControlEvent]]:
        bus = EventBus()
        osc_events: list[OscMessageEvent] = []
        control_events: list[ControlEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: osc_events.append(event))
        bus.subscribe(ControlEvent, lambda event: control_events.append(event))

        listen_port = _free_udp_port()
        adapter = OscAdapter(
            name="x32_foh",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "listen_host": "127.0.0.1",
                    "listen_port": listen_port,
                    "remote_host": "",
                    "remote_port": 0,
                },
            ),
            bus=bus,
        )

        await adapter.start()
        payload = encode_message("/ch/01/mix/01/level", [0.5])
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(payload, ("127.0.0.1", listen_port))
        for _ in range(20):
            if osc_events:
                break
            await asyncio.sleep(0.01)
        await adapter.stop()
        return osc_events, control_events

    osc_events, control_events = asyncio.run(scenario())

    assert len(osc_events) == 1
    assert osc_events[0].source == "x32_foh"
    assert osc_events[0].address == "/ch/01/mix/01/level"
    assert osc_events[0].direction == "input"
    assert len(control_events) == 1
    assert control_events[0].control == "/ch/01/mix/01/level"
    assert control_events[0].value == pytest.approx(0.5)


def test_osc_adapter_sends_mapped_events_to_remote() -> None:
    async def scenario() -> tuple[bytes, OscMessageEvent | None]:
        bus = EventBus()
        output_events: list[OscMessageEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: output_events.append(event))

        remote_port = _free_udp_port()
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", remote_port))
        receiver.settimeout(1.0)

        adapter = OscAdapter(
            name="x32_foh",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "listen_host": "127.0.0.1",
                    "listen_port": 0,
                    "remote_host": "127.0.0.1",
                    "remote_port": remote_port,
                },
            ),
            bus=bus,
        )

        await adapter.start()
        await adapter.send(
            MappedEvent(
                source="mapping",
                mapping_id="test",
                target="x32_foh:/ch/01/mix/01/level",
                value=0.25,
            )
        )
        await asyncio.sleep(0.05)
        try:
            data, _addr = receiver.recvfrom(4096)
        finally:
            receiver.close()
            await adapter.stop()

        output_event = next(
            (event for event in output_events if event.direction == "output"),
            None,
        )
        return data, output_event

    data, output_event = asyncio.run(scenario())

    assert output_event is not None
    assert output_event.address == "/ch/01/mix/01/level"
    assert output_event.arguments == (pytest.approx(0.25),)
    assert b"/ch/01/mix/01/level" in data


def test_osc_adapter_sends_wing_subscription_keepalive_to_desk() -> None:
    async def scenario() -> tuple[str, tuple[Any, ...], tuple[str, int]]:
        sent: list[tuple[bytes, tuple[str, int]]] = []

        class FakeTransport:
            def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
                sent.append((data, addr))

        adapter = OscAdapter(
            name="wing_foh",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "osc_port": 2223,
                    "remote_host": "192.168.1.48",
                    "osc_library": "behringer_wing",
                },
            ),
            bus=EventBus(),
        )
        adapter._transport = FakeTransport()  # noqa: SLF001
        await adapter._send_desk_keepalive()  # noqa: SLF001

        address, arguments = decode_messages(sent[0][0])[0]
        return address, arguments, sent[0][1]

    address, arguments, target = asyncio.run(scenario())

    assert address == "/%2223/*s~"
    assert arguments == ()
    assert target == ("192.168.1.48", 2223)


def test_osc_adapter_sends_xremote_keepalive_to_desk() -> None:
    async def scenario() -> tuple[str, tuple[Any, ...]]:
        sent: list[tuple[bytes, tuple[str, int]]] = []

        class FakeTransport:
            def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
                sent.append((data, addr))

        adapter = OscAdapter(
            name="x32_foh",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "osc_port": 10023,
                    "remote_host": "192.168.1.32",
                    "osc_library": "behringer_x32",
                },
            ),
            bus=EventBus(),
        )
        adapter._transport = FakeTransport()  # noqa: SLF001
        await adapter._send_desk_keepalive()  # noqa: SLF001

        address, arguments = decode_messages(sent[0][0])[0]
        return address, arguments

    address, arguments = asyncio.run(scenario())

    assert address == "/xremote"
    assert arguments == ()


def test_osc_adapter_reload_keeps_socket_when_bind_unchanged() -> None:
    async def scenario() -> tuple[Any, Any, bool, str]:
        listen_port = _free_udp_port()
        adapter = OscAdapter(
            name="wing_foh",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "listen_host": "127.0.0.1",
                    "osc_port": listen_port,
                    "remote_host": "192.168.1.48",
                    "osc_library": "behringer_wing",
                },
            ),
            bus=EventBus(),
        )

        await adapter.start()
        old_transport = adapter._transport  # noqa: SLF001
        await adapter.reload(
            AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "listen_host": "127.0.0.1",
                    "osc_port": listen_port,
                    "remote_host": "192.168.1.50",
                    "osc_library": "behringer_wing",
                },
            )
        )
        return old_transport, adapter._transport, adapter.running, adapter._remote_host  # noqa: SLF001

    old_transport, new_transport, running, remote_host = asyncio.run(scenario())

    assert running
    assert old_transport is new_transport
    assert remote_host == "192.168.1.50"


def test_osc_adapter_reload_rebinds_when_listen_port_changes() -> None:
    async def scenario() -> tuple[Any, Any]:
        first_port = _free_udp_port()
        second_port = _free_udp_port()
        while second_port == first_port:
            second_port = _free_udp_port()

        adapter = OscAdapter(
            name="osc",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "listen_host": "127.0.0.1",
                    "listen_port": first_port,
                    "remote_host": "",
                    "remote_port": 0,
                },
            ),
            bus=EventBus(),
        )

        await adapter.start()
        old_transport = adapter._transport  # noqa: SLF001
        await adapter.reload(
            AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "listen_host": "127.0.0.1",
                    "listen_port": second_port,
                    "remote_host": "",
                    "remote_port": 0,
                },
            )
        )
        return old_transport, adapter._transport

    old_transport, new_transport = asyncio.run(scenario())

    assert old_transport is not new_transport
    assert new_transport is not None


def test_osc_adapter_proxy_forwards_client_and_desk_messages() -> None:
    async def scenario() -> tuple[list[tuple[bytes, tuple[str, int]]], int]:
        sent: list[tuple[bytes, tuple[str, int]]] = []

        class FakeTransport:
            def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
                sent.append((data, addr))

        adapter = OscAdapter(
            name="wing_foh",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "osc_port": 2223,
                    "remote_host": "192.168.1.48",
                    "osc_library": "behringer_wing",
                    "desk_proxy_mode": True,
                },
            ),
            bus=EventBus(),
        )
        adapter._transport = FakeTransport()  # noqa: SLF001
        adapter.running = True

        client_payload = encode_message("/ch/1/fdr", [0.25])
        await adapter.handle_datagram(client_payload, ("192.168.1.10", 40000))

        desk_payload = encode_message("/ch/1/fdr", [0.5])
        await adapter.handle_datagram(desk_payload, ("192.168.1.48", 2223))

        return sent, adapter.desk_proxy_client_count

    sent, client_count = asyncio.run(scenario())

    assert client_count == 1
    assert sent[0][1] == ("192.168.1.48", 2223)
    assert sent[1][1] == ("192.168.1.10", 40000)
    assert b"/ch/1/fdr" in sent[0][0]
    assert b"/ch/1/fdr" in sent[1][0]
