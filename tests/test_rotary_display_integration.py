"""Integration coverage for rotary display host/device protocol."""

from __future__ import annotations

import asyncio
from collections import deque

import pytest

from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointId, DataPointValue, ValueType
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


def test_serial_beat_coalesces_catch_up_during_in_flight_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()
    original_send_beat = RotaryDisplayModule._send_beat

    async def slow_send_beat(self, value: float) -> None:
        await asyncio.sleep(0.02)
        await original_send_beat(self, value)

    monkeypatch.setattr(RotaryDisplayModule, "_send_beat", slow_send_beat)

    async def scenario() -> None:
        module._schedule_beat_send(1.0)
        await asyncio.sleep(0.005)
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n", "beat 1.0\n"]


def test_serial_beat_sends_each_queued_edge_without_coalescing() -> None:
    serial_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        for _ in range(3):
            module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n", "beat 1.0\n", "beat 1.0\n"]


def test_serial_beat_coalesces_only_while_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()
    original_send_beat = RotaryDisplayModule._send_beat

    async def slow_send_beat(self, value: float) -> None:
        await asyncio.sleep(0.02)
        await original_send_beat(self, value)

    monkeypatch.setattr(RotaryDisplayModule, "_send_beat", slow_send_beat)

    async def scenario() -> None:
        module._schedule_beat_send(1.0)
        await asyncio.sleep(0.005)
        module._schedule_beat_send(1.0)
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n", "beat 1.0\n"]


def test_serial_beat_sends_immediately_without_gap_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []
    sleep_log: list[float] = []

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
    master_clock.running = True

    async def fake_sleep(duration: float) -> None:
        sleep_log.append(duration)

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.asyncio.sleep",
        fake_sleep,
    )

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n", "beat 1.0\n"]
    assert sleep_log == []


def test_serial_beat_delivers_each_edge_when_task_is_idle_between_beats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        for _ in range(3):
            module._schedule_beat_send(1.0)
            if module._beat_send_task is not None:
                await module._beat_send_task

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n", "beat 1.0\n", "beat 1.0\n"]


def test_same_tick_beat_delivers_each_queued_serial_edge() -> None:
    serial_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module._schedule_beat_send(1.0)
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n", "beat 1.0\n"]


def test_serial_beat_delivers_steady_one_per_tick_at_170_bpm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []
    send_times: list[float] = []
    clock = {"now": 0.0}

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    master_clock.running = True
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.time.monotonic",
        lambda: clock["now"],
    )

    class FakeSerial:
        def write(self, data: bytes) -> int:
            send_times.append(clock["now"])
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()
    beat_interval = 60.0 / 170.0

    async def scenario() -> None:
        for _ in range(9):
            module._schedule_beat_send(1.0)
            if module._beat_send_task is not None:
                await module._beat_send_task
            clock["now"] += beat_interval

    asyncio.run(scenario())

    beat_lines = [line for line in serial_payloads if line.startswith("beat ")]
    assert len(beat_lines) == 9
    gaps = [send_times[i + 1] - send_times[i] for i in range(len(send_times) - 1)]
    assert all(gap == pytest.approx(beat_interval, abs=0.001) for gap in gaps)


def test_pending_beats_cleared_when_clock_stops() -> None:
    serial_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module._beat_outbox.extend([1.0, 1.0, 1.0])
        module._pending_beat_value = 1.0
        master_clock.running = False
        await module._cancel_beat_delivery(send_off=True)

    asyncio.run(scenario())

    assert module._beat_outbox == deque()
    assert module._pending_beat_value is None
    assert serial_payloads == ["beat 0.0\n"]


def test_running_feedback_clears_pending_beats() -> None:
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
    master_clock.running = False

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module._beat_outbox.extend([1.0, 1.0])
        await module._on_feedback(
            DataPointValue(
                point_id=DataPointId("rotary_display", "running"),
                value_type=ValueType.BOOL,
                bool_value=False,
            )
        )

    asyncio.run(scenario())

    assert module._beat_outbox == deque()
    assert serial_payloads == ["beat 0.0\n", "sync 120.0 0 0 quarter\n"]


def test_serial_beat_delivers_nine_of_nine_at_170_bpm(monkeypatch: pytest.MonkeyPatch) -> None:
    serial_payloads: list[str] = []
    clock = {"now": 0.0}

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 170.0},
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
    master_clock.running = True
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.time.monotonic",
        lambda: clock["now"],
    )

    async def fake_sleep(duration: float) -> None:
        clock["now"] += duration

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.asyncio.sleep",
        fake_sleep,
    )

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        interval = 60.0 / 170.0
        for _ in range(9):
            module._schedule_beat_send(1.0)
            if module._beat_send_task is not None:
                await module._beat_send_task
            clock["now"] += interval

    asyncio.run(scenario())

    assert len(serial_payloads) == 9


def test_protocol_matches_documentation_example() -> None:
    line = format_sync_line(
        RotarySyncState(bpm=120.0, running=True, click_enabled=False, click_interval="quarter")
    )
    assert line == "sync 120.0 1 0 quarter"


def test_tap_tempo_ignored_within_cooldown_after_device_set_bpm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.time.monotonic",
        lambda: clock["now"],
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0, "tap_tempo_min_taps": 3},
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
    module._serial_connected = True

    async def scenario() -> None:
        await module._handle_serial_line("bpm 141.0\n")
        clock["now"] = 100.231
        await module._handle_serial_line("tap_tempo\n")

    asyncio.run(scenario())

    assert master_clock.bpm == pytest.approx(141.0)


def test_tap_tempo_allowed_after_device_set_bpm_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.time.monotonic",
        lambda: clock["now"],
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0, "tap_tempo_min_taps": 3},
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
    module._serial_connected = True
    handled: list[str] = []
    original_handle = master_clock.handle_command

    async def track_handle(event):
        handled.append(event.command)
        return await original_handle(event)

    master_clock.handle_command = track_handle  # type: ignore[method-assign]

    async def scenario() -> None:
        await module._handle_serial_line("bpm 141.0\n")
        clock["now"] = 100.231
        await module._handle_serial_line("tap_tempo\n")
        clock["now"] = 103.5
        await module._handle_serial_line("tap_tempo\n")

    asyncio.run(scenario())

    assert handled == ["set_bpm", "tap_tempo"]


def test_production_config_sends_beats_on_serial_without_feedback_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []

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
    module.running = True
    module._serial_connected = True
    master_clock.running = True

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    module._serial_port = FakeSerial()

    async def scenario() -> None:
        module._schedule_beat_send(1.0)
        if module._beat_send_task is not None:
            await module._beat_send_task

    asyncio.run(scenario())

    assert serial_payloads == ["beat 1.0\n"]


def test_transport_beat_listener_sends_serial_on_click_tick_at_170_bpm() -> None:
    serial_payloads: list[str] = []

    class FakeClickPlayer:
        def trigger(self) -> None:
            return

        async def play(self) -> None:
            return

        async def close(self) -> None:
            return

    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 170.0,
                "click_enabled": True,
                "click_interval": "quarter",
            },
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/ttyACM0",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus, click_player=FakeClickPlayer())
    clock_gen = MasterClockGenerator(master_clock, store)
    store.register_many(clock_gen.datapoints())
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    async def scenario() -> None:
        master_clock.bind_datapoint_sink(clock_gen)
        await clock_gen.start()
        master_clock.register_beat_pulse_listener(module._on_transport_beat_pulse)
        module.running = True
        module._serial_connected = True
        module._serial_port = FakeSerial()
        await master_clock.start_transport(reset_position=True)
        await asyncio.sleep(3.2)
        await master_clock.stop_transport(send_transport=False)
        master_clock.unregister_beat_pulse_listener(module._on_transport_beat_pulse)

    asyncio.run(scenario())

    beat_lines = [line for line in serial_payloads if line.startswith("beat ")]
    assert len(beat_lines) >= 9
