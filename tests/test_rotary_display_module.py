import asyncio

import pytest

from midijuggler.config import MasterClockConfig, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.events import OscMessageEvent
from midijuggler.master_clock import MasterClock
from midijuggler.modules.generator.master_clock import MasterClockGenerator
from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
from midijuggler.osc.protocol import decode_messages


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

    def fake_udp(payload: bytes, host: str, port: int) -> None:
        sent.append((payload, host, port))

    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module._udp_send",
        fake_udp,
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
                arguments=("192.168.1.50", 9001),
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
    assert sent[0][1:] == ("192.168.1.50", 9001)


def test_rotary_display_serial_command_updates_bpm(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def scenario() -> None:
        await generator.start()
        await module.start()
        await module._handle_serial_line("bpm 140.0\n")
        await module.stop()
        await generator.stop()

    asyncio.run(scenario())
    assert master_clock.bpm == pytest.approx(140.0)
