"""Integration coverage for rotary display host/device protocol."""

from __future__ import annotations

import asyncio

import pytest

from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.generator.master_clock import MasterClockGenerator
from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
from midijuggler.modules.interface.rotary_display.protocol import format_sync_line, RotarySyncState
from midijuggler.osc.protocol import decode_messages


def test_serial_and_osc_feedback_both_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[bytes, str, int]] = []
    serial_payloads: list[str] = []

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        lambda payload, host, port, **kwargs: sent.append((payload, host, port)),
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "both",
                "feedback_host": "192.168.1.50",
                "feedback_port": 9001,
                "serial_port": "",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    generator = MasterClockGenerator(master_clock, store)
    store.register_many(generator.datapoints())
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._serial_connected = True
    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        await generator.start()
        await module.start()
        await module._send_sync(force=True)
        await module.stop()
        await generator.stop()

    asyncio.run(scenario())

    assert sent
    address, args = decode_messages(sent[0][0])[0]
    assert address == "/midijuggler/rotary/sync"
    assert args[0] == pytest.approx(120.0)
    assert serial_payloads
    assert serial_payloads[0].startswith("sync ")


def test_beat_uses_osc_only_when_both_transports_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[bytes, str, int]] = []
    serial_payloads: list[str] = []

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        lambda payload, host, port, **kwargs: sent.append((payload, host, port)),
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "both",
                "feedback_host": "192.168.1.50",
                "feedback_port": 9001,
                "serial_port": "/dev/ttyACM0",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._serial_connected = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module.running = True
        await module._send_beat(1.0)

    asyncio.run(scenario())

    assert len(sent) == 1
    address, args = decode_messages(sent[0][0])[0]
    assert address == "/midijuggler/rotary/beat"
    assert args[0] == pytest.approx(1.0)
    assert not serial_payloads


def test_beat_falls_back_to_serial_when_both_without_feedback_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[bytes, str, int]] = []
    serial_payloads: list[str] = []

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        lambda payload, host, port, **kwargs: sent.append((payload, host, port)),
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "both",
                "feedback_host": "",
                "feedback_port": 9001,
                "serial_port": "/dev/ttyACM0",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._serial_connected = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module.running = True
        await module._send_beat(1.0)

    asyncio.run(scenario())

    assert not sent
    assert serial_payloads == ["beat 1.0\n"]


def test_serial_beat_coalesces_catch_up_during_in_flight_send() -> None:
    serial_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/ttyACM0",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module.running = True
    module._serial_connected = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module._beat_outbox.append(1.0)
        await module._drain_pending_beat_sends()
        module._pending_beat_value = 1.0
        module._beats_received_during_send = 2
        await module._drain_pending_beat_sends()

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n"]


def test_serial_beat_skips_catch_up_within_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    serial_payloads: list[str] = []
    clock = {"now": 0.0}

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/ttyACM0",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module.running = True
    module._serial_connected = True
    module._last_beat_serial_sent_at = 0.0
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.time.monotonic",
        lambda: clock["now"],
    )

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module._beat_outbox.append(1.0)
        await module._drain_pending_beat_sends()
        clock["now"] = 0.05
        module._pending_beat_value = 1.0
        module._beats_received_during_send = 2
        await module._drain_pending_beat_sends()

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n"]


def test_protocol_matches_documentation_example() -> None:
    line = format_sync_line(
        RotarySyncState(bpm=120.0, running=True, click_enabled=False, click_interval="quarter")
    )
    assert line == "sync 120.0 1 0 quarter"
