import asyncio
import logging
from dataclasses import replace

import pytest

from midijuggler.config import MasterClockConfig, parse_config
from midijuggler.datapoint.bridge import EventToDataPointBridge
from midijuggler.datapoint.migrate import effective_connections
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointId, float_value
from midijuggler.device.points import build_device_datapoints
from midijuggler.device.registry import DeviceRegistry
from midijuggler.eventbus import EventBus
from midijuggler.events import MasterClockCommandEvent, OscMessageEvent
from midijuggler.master_clock import MasterClock, click_interval_to_set_value
from midijuggler.modules.generator.master_clock import MasterClockGenerator
from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.osc.protocol import decode_messages

from conftest import osc_device


def test_rotary_display_sync_uses_master_clock_bpm_when_store_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[bytes, str, int]] = []

    def fake_udp(payload: bytes, host: str, port: int, **kwargs: object) -> None:
        sent.append((payload, host, port))

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        fake_udp,
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "osc",
                "feedback_host": "192.168.1.70",
                "feedback_port": 9001,
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._last_sync = None

    async def scenario() -> None:
        await module.start()
        master_clock.bpm = 132.0
        await store.write(float_value(DataPointId("rotary_display", "bpm"), 120.0))
        await store.write(float_value(DataPointId("rotary_display", "running"), 0.0))
        await module.stop()

    asyncio.run(scenario())

    sync_messages = [
        decode_messages(payload)[0]
        for payload, _, _ in sent
        if decode_messages(payload)[0][0] == "/midijuggler/rotary/sync"
    ]
    assert sync_messages
    assert sync_messages[-1][1][0] == pytest.approx(132.0)


def test_rotary_display_sync_on_clock_bpm_datapoint_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_bpms: list[float] = []

    def track_sync(self, state) -> bool:
        sync_bpms.append(state.bpm)
        return True

    monkeypatch.setattr(RotaryDisplayModule, "_write_sync_osc_sync", track_sync)

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "osc",
                "feedback_host": "192.168.1.70",
                "feedback_port": 9001,
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._last_sync = None

    async def scenario() -> None:
        await module.start()
        master_clock.bpm = 145.0
        await store.write(float_value(DataPointId("clock", "bpm"), 145.0))
        await module.stop()

    asyncio.run(scenario())

    assert sync_bpms
    assert sync_bpms[-1] == pytest.approx(145.0)


def test_rotary_display_publishes_new_bpm_after_encoder_osc_when_clock_already_updated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[bytes, str, int]] = []

    def fake_udp(payload: bytes, host: str, port: int, **kwargs: object) -> None:
        sent.append((payload, host, port))

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        fake_udp,
    )

    config = parse_config(
        {
            "runtime": {"datapoint_routing": True},
            "master_clock": {"enabled": True, "bpm": 120.0},
            "adapters": {"osc": {"enabled": True, "type": "osc"}},
            "devices": [osc_device("rotary_encoder", "rotary_display", adapter="osc")],
            "rotary_display": {
                "enabled": True,
                "transport": "osc",
                "feedback_host": "192.168.1.70",
                "feedback_port": 9001,
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    registry = DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter("osc")
    specs, _ = build_device_datapoints(device, config.adapters["osc"])
    store.register_many(specs)

    master_clock = MasterClock(config.master_clock, bus)
    generator = MasterClockGenerator(master_clock, store)
    master_clock.bind_datapoint_sink(generator)
    store.register_many(generator.datapoints())
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    graph = ModifierGraph(store, effective_connections(config))
    bridge = EventToDataPointBridge(store, bus, registry)

    async def scenario() -> None:
        await generator.start()
        await graph.start()
        await module.start()
        await bridge._on_osc_message(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/clock/bpm",
                arguments=(132.0,),
                direction="input",
            )
        )
        await asyncio.sleep(0)
        await module.stop()
        await graph.stop()
        await generator.stop()

    asyncio.run(scenario())

    assert master_clock.bpm == pytest.approx(132.0)
    assert store.float_value("clock.bpm") == pytest.approx(132.0)
    sync_messages = [
        decode_messages(payload)[0]
        for payload, _, _ in sent
        if decode_messages(payload)[0][0] == "/midijuggler/rotary/sync"
    ]
    assert sync_messages
    assert sync_messages[-1][1][0] == pytest.approx(132.0)


def test_parse_rotary_display_config() -> None:
    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "transport": "both",
                "serial_port": "/dev/ttyACM0",
            }
        }
    )
    assert config.rotary_display.enabled is True
    assert config.rotary_display.transport == "both"
    assert config.rotary_display.serial_port == "/dev/ttyACM0"


def test_rotary_display_registers_feedback_from_hello(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[bytes, str, int]] = []

    def fake_udp(payload: bytes, host: str, port: int, **kwargs: object) -> None:
        sent.append((payload, host, port))

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        fake_udp,
    )
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.resolve_mdns_ipv4",
        lambda host, force=False: None,
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {"enabled": True, "transport": "osc"},
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    generator = MasterClockGenerator(master_clock, store)
    store.register_many(generator.datapoints())
    module = RotaryDisplayModule(
        store,
        config.rotary_display,
        master_clock,
        bus,
    )

    async def scenario() -> None:
        await generator.start()
        await module.start()
        await bus.publish(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/rotary/hello",
                arguments=("rotary-stage-left.local", 9001),
                direction="input",
            )
        )
        await asyncio.sleep(0)
        await module.stop()
        await generator.stop()

    asyncio.run(scenario())

    assert sent
    address, _args = decode_messages(sent[0][0])[0]
    assert address == "/midijuggler/rotary/sync"
    assert sent[0][1:] == ("rotary-stage-left.local", 9001)


def test_rotary_display_hello_registers_feedback_handler() -> None:
    registered: list[tuple[str, int]] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {"enabled": True, "transport": "osc"},
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module.set_feedback_registration_handler(
        lambda host, port: registered.append((host, port))
    )

    async def scenario() -> None:
        await module.start()
        await bus.publish(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/rotary/hello",
                arguments=("192.168.1.60", 9001),
                direction="input",
            )
        )
        await asyncio.sleep(0)
        await module.stop()

    asyncio.run(scenario())

    assert registered == [("192.168.1.60", 9001)]


def test_rotary_display_duplicate_hello_logs_debug_not_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {"enabled": True, "transport": "osc"},
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

    hello = OscMessageEvent(
        source="osc",
        address="/midijuggler/rotary/hello",
        arguments=("rotary-267248.local", 9001),
        direction="input",
    )

    async def scenario() -> None:
        await module.start()
        with caplog.at_level(logging.DEBUG, logger="midijuggler.modules.interface.rotary_display.module"):
            await module._on_osc_message(hello)
            await module._on_osc_message(hello)
        await module.stop()

    asyncio.run(scenario())

    registration_logs = [
        record
        for record in caplog.records
        if "rotary display" in record.message and "registered" in record.message
    ]
    assert len(registration_logs) == 2
    assert registration_logs[0].levelno == logging.INFO
    assert registration_logs[1].levelno == logging.DEBUG


def test_rotary_display_pushes_initial_sync_on_start_with_feedback_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[bytes, str, int]] = []

    def fake_udp(payload: bytes, host: str, port: int, **kwargs: object) -> None:
        sent.append((payload, host, port))

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        fake_udp,
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 132.0},
            "rotary_display": {
                "enabled": True,
                "transport": "osc",
                "feedback_host": "192.168.1.70",
                "feedback_port": 9001,
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

    async def scenario() -> None:
        await module.start()
        await asyncio.sleep(0)
        await module.stop()

    asyncio.run(scenario())

    assert len(sent) == 1
    address, args = decode_messages(sent[0][0])[0]
    assert address == "/midijuggler/rotary/sync"
    assert args[0] == pytest.approx(132.0)
    assert sent[0][1:] == ("192.168.1.70", 9001)


def test_rotary_display_hello_resolves_mdns_feedback_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.resolve_mdns_ipv4",
        lambda host, force=False: "192.168.0.42",
    )

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {"enabled": True, "transport": "osc"},
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

    async def scenario() -> None:
        await module.start()
        await bus.publish(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/rotary/hello",
                arguments=("rotary-267248.local", 9001),
                direction="input",
            )
        )
        await asyncio.sleep(0)
        await module.stop()

    asyncio.run(scenario())

    assert module._feedback_host == "rotary-267248.local"
    assert module._feedback_host_ip == "192.168.0.42"


def test_rotary_display_pushes_config_on_serial_hello(monkeypatch: pytest.MonkeyPatch) -> None:
    push_calls: list[bool] = []

    async def fake_push(*, force: bool = False) -> dict:
        push_calls.append(force)
        return {"pushed": True}

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/null",
                "device": {"host": "midijuggler.local"},
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._serial_connected = True
    monkeypatch.setattr(module, "push_device_config", fake_push)

    async def noop_sync(**kwargs: object) -> None:
        return None

    monkeypatch.setattr(module, "_send_sync", noop_sync)

    async def scenario() -> None:
        await module._handle_serial_line("hello\n")

    asyncio.run(scenario())
    assert push_calls == [False]


def test_rotary_display_serial_command_updates_bpm(monkeypatch: pytest.MonkeyPatch) -> None:
    sync_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/null",
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    generator = MasterClockGenerator(master_clock, store)
    store.register_many(generator.datapoints())
    module = RotaryDisplayModule(
        store,
        config.rotary_display,
        master_clock,
        bus,
    )
    module._serial_connected = True

    async def capture_sync(payload: str) -> None:
        sync_payloads.append(payload)

    monkeypatch.setattr(module, "_send_serial", capture_sync)

    async def scenario() -> None:
        await generator.start()
        await module.start()
        await module._handle_serial_line("bpm 140.0\n")
        await module.stop()
        await generator.stop()

    asyncio.run(scenario())
    assert master_clock.bpm == pytest.approx(140.0)
    sync_lines = [payload for payload in sync_payloads if payload.startswith("sync ")]
    assert sync_lines
    assert "sync 140.0" in sync_lines[-1]


def test_rotary_display_serial_open_uses_no_dtr() -> None:
    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/null",
            }
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(MasterClockConfig(), bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

    captured: dict[str, object] = {}

    class FakeSerial:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

    import sys

    fake_serial = type(sys)("serial")
    fake_serial.Serial = FakeSerial
    sys.modules["serial"] = fake_serial
    try:
        module._open_serial_port("/dev/null")
    finally:
        del sys.modules["serial"]

    assert captured["kwargs"]["dsrdtr"] is False
    assert captured["kwargs"]["rtscts"] is False


def test_rotary_display_syncs_click_interval_from_clock_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_payloads: list[str] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0, "click_interval": "quarter"},
            "rotary_display": {"enabled": True, "transport": "serial", "serial_port": ""},
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    generator = MasterClockGenerator(master_clock, store)
    store.register_many(generator.datapoints())
    graph = ModifierGraph(store, effective_connections(config))
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._serial_connected = True

    async def capture_sync(payload: str) -> None:
        sync_payloads.append(payload)

    monkeypatch.setattr(module, "_send_serial", capture_sync)

    async def scenario() -> None:
        await generator.start()
        await graph.start()
        await module.start()
        await store.write(
            float_value(
                DataPointId("clock", "click_interval_set"),
                click_interval_to_set_value("eighth"),
            )
        )
        await asyncio.sleep(0)
        await module.stop()
        await graph.stop()
        await generator.stop()

    asyncio.run(scenario())

    sync_lines = [payload for payload in sync_payloads if payload.startswith("sync ")]
    assert sync_lines
    assert "eighth" in sync_lines[-1]


def test_apply_runtime_config_starts_serial_when_enabling_host_transport() -> None:
    async def scenario() -> None:
        config = parse_config(
            {
                "rotary_display": {
                    "enabled": True,
                    "transport": "osc",
                    "serial_port": "/dev/ttyACM0",
                }
            }
        )
        store = DataPointStore()
        bus = EventBus()
        master_clock = MasterClock(MasterClockConfig(enabled=True), bus)
        module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

        loop_started = asyncio.Event()

        async def fake_serial_loop() -> None:
            module._serial_connected = True
            module._serial_port = object()
            loop_started.set()
            await asyncio.Event().wait()

        module._serial_loop = fake_serial_loop  # type: ignore[method-assign]

        await module.start()
        assert module._serial_task is None

        serial_config = replace(config.rotary_display, transport="serial")
        await module.apply_runtime_config(serial_config)

        assert module._use_serial is True
        assert module._serial_task is not None
        await asyncio.wait_for(loop_started.wait(), timeout=1.0)
        await module.stop()

    asyncio.run(scenario())


def test_push_device_config_waits_for_serial_after_runtime_enable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push_calls: list[list[str]] = []

    async def scenario() -> dict:
        config = parse_config(
            {
                "rotary_display": {
                    "enabled": True,
                    "transport": "osc",
                    "serial_port": "/dev/ttyACM0",
                    "device": {"transport": "serial"},
                }
            }
        )
        store = DataPointStore()
        bus = EventBus()
        master_clock = MasterClock(MasterClockConfig(enabled=True), bus)
        module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

        async def fake_serial_loop() -> None:
            await asyncio.sleep(0.2)
            module._serial_connected = True
            module._serial_port = object()
            await asyncio.Event().wait()

        module._serial_loop = fake_serial_loop  # type: ignore[method-assign]

        def fake_push_sync(port: object, commands: list[str], *, timeout_s: float = 3.0) -> dict:
            push_calls.append(commands)
            return {"ok": True, "responses": ["ok"]}

        monkeypatch.setattr(
            "midijuggler.modules.interface.rotary_display.module.push_device_config_sync",
            fake_push_sync,
        )

        await module.start()
        serial_config = replace(config.rotary_display, transport="serial")
        await module.apply_runtime_config(serial_config)
        result = await module.push_device_config(force=True)
        await module.stop()
        return result

    result = asyncio.run(scenario())

    assert result["pushed"] is True


def test_apply_runtime_config_enables_osc_and_pokes_device_hello(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_payloads: list[str] = []
    sync_calls: list[bool] = []

    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/ttyACM0",
                "feedback_host": "192.168.1.70",
                "feedback_port": 9001,
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

    class FakeSerial:
        def write(self, data: bytes) -> int:
            serial_payloads.append(data.decode())
            return len(data)

    async def track_send_sync(self, *, force: bool = False) -> None:
        sync_calls.append(force)

    monkeypatch.setattr(RotaryDisplayModule, "_send_sync", track_send_sync)

    async def noop_wait(self, *, timeout_s: float) -> None:
        return None

    monkeypatch.setattr(RotaryDisplayModule, "_wait_for_osc_hello", noop_wait)

    async def scenario() -> None:
        await module.start()
        module._serial_connected = True
        module._serial_port = FakeSerial()
        osc_config = replace(config.rotary_display, transport="osc")
        await module.apply_runtime_config(osc_config)
        await module.stop()

    asyncio.run(scenario())

    assert "hello\n" in serial_payloads
    assert sync_calls == [True]


def test_push_device_config_uses_usb_when_host_transport_is_osc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> dict:
        config = parse_config(
            {
                "rotary_display": {
                    "enabled": True,
                    "transport": "serial",
                    "serial_port": "/dev/ttyACM0",
                    "device": {"transport": "wifi"},
                }
            }
        )
        store = DataPointStore()
        bus = EventBus()
        master_clock = MasterClock(MasterClockConfig(enabled=True), bus)
        module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
        module._serial_connected = True
        module._serial_port = object()

        push_calls: list[list[str]] = []

        def fake_push_sync(port: object, commands: list[str], *, timeout_s: float = 3.0) -> dict:
            push_calls.append(commands)
            return {"ok": True, "responses": ["ok"]}

        monkeypatch.setattr(
            "midijuggler.modules.interface.rotary_display.module.push_device_config_sync",
            fake_push_sync,
        )

        await module.start()
        osc_config = replace(config.rotary_display, transport="osc")
        module.update_config(osc_config)

        async def noop_wait(self, *, timeout_s: float) -> None:
            return None

        monkeypatch.setattr(RotaryDisplayModule, "_wait_for_osc_hello", noop_wait)

        result = await module.push_device_config(force=True)
        await module.apply_runtime_config(osc_config)
        await module.stop()
        return result

    result = asyncio.run(scenario())

    assert result["pushed"] is True


def test_beat_osc_sync_uses_cached_ip_without_mdns_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket as socket_module

    resolve_calls: list[str] = []
    sent_targets: list[tuple[str, int]] = []

    def fake_resolve(host: str, **kwargs: object) -> str:
        resolve_calls.append(host)
        return "192.168.1.99"

    class FakeSocket:
        def sendto(self, payload: bytes, addr: tuple[str, int]) -> int:
            sent_targets.append(addr)
            return len(payload)

        def close(self) -> None:
            return None

    real_socket = socket_module.socket

    def fake_socket(family: int, sock_type: int, *args: object, **kwargs: object):
        if family == socket_module.AF_INET and sock_type == socket_module.SOCK_DGRAM:
            return FakeSocket()
        return real_socket(family, sock_type, *args, **kwargs)

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.resolve_udp_host",
        fake_resolve,
    )
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.socket.socket",
        fake_socket,
    )

    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "transport": "osc",
                "feedback_host": "rotary-stage.local",
                "feedback_port": 9001,
            }
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(MasterClockConfig(enabled=True), bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._feedback_host = "rotary-stage.local"
    module._feedback_host_ip = "192.168.1.70"
    module._feedback_port = 9001
    module.running = True

    module._write_beat_osc_sync(1.0)

    assert sent_targets == [("192.168.1.70", 9001)]
    assert resolve_calls == []


def test_beat_osc_sync_skips_unresolved_mdns_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket as socket_module

    resolve_calls: list[str] = []
    sent_targets: list[tuple[str, int]] = []

    def fake_resolve(host: str, **kwargs: object) -> str:
        resolve_calls.append(host)
        return "192.168.1.99"

    class FakeSocket:
        def sendto(self, payload: bytes, addr: tuple[str, int]) -> int:
            sent_targets.append(addr)
            return len(payload)

        def close(self) -> None:
            return None

    real_socket = socket_module.socket

    def fake_socket(family: int, sock_type: int, *args: object, **kwargs: object):
        if family == socket_module.AF_INET and sock_type == socket_module.SOCK_DGRAM:
            return FakeSocket()
        return real_socket(family, sock_type, *args, **kwargs)

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.resolve_udp_host",
        fake_resolve,
    )
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.socket.socket",
        fake_socket,
    )

    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "transport": "osc",
                "feedback_host": "rotary-stage.local",
                "feedback_port": 9001,
            }
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(MasterClockConfig(enabled=True), bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._feedback_host = "rotary-stage.local"
    module._feedback_port = 9001
    module.running = True

    module._write_beat_osc_sync(1.0)

    assert sent_targets == []
    assert resolve_calls == []


def test_register_feedback_target_preserves_cached_ip_on_reregister() -> None:
    config = parse_config({"rotary_display": {"enabled": True, "transport": "osc"}})
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(MasterClockConfig(enabled=True), bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)
    module._feedback_host = "rotary-stage.local"
    module._feedback_host_ip = "192.168.1.70"

    module._register_feedback_target("rotary-stage.local", 9001)

    assert module._feedback_host_ip == "192.168.1.70"


def test_enable_host_osc_transport_aligns_serial_device_and_waits_for_hello(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push_calls: list[bool] = []
    wait_timeouts: list[float] = []

    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "transport": "serial",
                "serial_port": "/dev/ttyACM0",
                "device": {"transport": "serial", "wifi_enabled": True},
            }
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(MasterClockConfig(enabled=True), bus)
    module = RotaryDisplayModule(store, config.rotary_display, master_clock, bus)

    class FakeSerial:
        def write(self, data: bytes) -> int:
            return len(data)

    module._serial_connected = True
    module._serial_port = FakeSerial()

    async def fake_push(self, *, force: bool = False) -> dict[str, object]:
        push_calls.append(force)
        assert self.config.device.transport == "wifi"
        return {"pushed": True}

    async def fake_wait(self, *, timeout_s: float) -> None:
        wait_timeouts.append(timeout_s)
        self._osc_hello_event.set()

    monkeypatch.setattr(RotaryDisplayModule, "push_device_config", fake_push)
    monkeypatch.setattr(RotaryDisplayModule, "_wait_for_osc_hello", fake_wait)
    monkeypatch.setattr(RotaryDisplayModule, "_send_sync", lambda self, **kwargs: asyncio.sleep(0))

    async def scenario() -> None:
        await module.start()
        osc_config = replace(config.rotary_display, transport="osc")
        await module.apply_runtime_config(osc_config)
        await module.stop()

    asyncio.run(scenario())

    assert push_calls == [True]
    assert wait_timeouts == [12.0]
    assert module.config.device.transport == "wifi"
