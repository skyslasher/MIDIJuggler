import asyncio
import socket
from unittest.mock import AsyncMock

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AdapterConfig, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import OscMessageEvent
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_send_osc_adapter_test_message_publishes_output_event() -> None:
    async def scenario() -> OscMessageEvent | None:
        listen_port = _free_udp_port()
        bus = EventBus()
        events: list[OscMessageEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: events.append(event))

        adapter = OscAdapter(
            name="wing_foh",
            config=AdapterConfig(
                enabled=True,
                kind="osc",
                options={
                    "osc_port": listen_port,
                    "listen_host": "127.0.0.1",
                    "remote_host": "127.0.0.1",
                    "osc_library": "behringer_wing",
                },
            ),
            bus=bus,
        )
        await adapter.start()

        interface = WebInterface(
            parse_config({"adapters": {}}),
            bus,
            ClockBpmTracker(),
            MasterClock(parse_config({"adapters": {}}).master_clock, bus),
            osc_adapters={"wing_foh": adapter},
        )

        await interface.send_osc_adapter_test_message(
            {
                "name": "wing_foh",
                "address": "/ch/1/fdr~~~",
                "value": 0.5,
            }
        )
        await adapter.stop()
        return next((event for event in events if event.direction == "output"), None)

    output_event = asyncio.run(scenario())

    assert output_event is not None
    assert output_event.address == "/ch/1/fdr~~~"
    assert output_event.arguments == (pytest.approx(0.5),)


def test_send_osc_adapter_test_message_starts_newly_saved_instance() -> None:
    async def scenario() -> dict[str, object]:
        listen_port = _free_udp_port()
        bus = EventBus()
        config = parse_config({"adapters": {}})
        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
        )

        await interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "x32",
                        "enabled": True,
                        "desk_mode": "x32",
                        "listen_host": "127.0.0.1",
                        "osc_port": listen_port,
                        "remote_host": "192.168.10.32",
                    }
                ]
            }
        )

        return await interface.send_osc_adapter_test_message(
            {
                "name": "x32",
                "address": "/ch/01/mix/01/level",
                "value": 0.5,
            }
        )

    result = asyncio.run(scenario())

    assert result["ok"] is True
    assert result["name"] == "x32"


def test_send_osc_adapter_test_message_reports_disabled_instance() -> None:
    config = parse_config(
        {
            "adapters": {
                "x32": {
                    "enabled": False,
                    "type": "osc",
                    "osc_library": "behringer_x32",
                    "osc_port": 10023,
                    "remote_host": "192.168.10.32",
                }
            }
        }
    )
    interface = WebInterface(
        config,
        bus=EventBus(),
        clock=ClockBpmTracker(),
        master_clock=MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="disabled"):
        asyncio.run(
            interface.send_osc_adapter_test_message(
                {
                    "name": "x32",
                    "address": "/ch/01/mix/01/level",
                    "value": 0.5,
                }
            )
        )


def test_send_midi_adapter_test_message_uses_adapter_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> AsyncMock:
        bus = EventBus()
        adapter = MidiAdapter(
            name="stage_midi",
            config=AdapterConfig(
                enabled=True,
                kind="midi",
                options={"output_port": "Stage MIDI Out"},
            ),
            bus=bus,
        )
        adapter.running = True
        send_mock = AsyncMock()
        monkeypatch.setattr(adapter, "send_test_message", send_mock)

        interface = WebInterface(
            parse_config({"adapters": {}}),
            bus,
            ClockBpmTracker(),
            MasterClock(parse_config({"adapters": {}}).master_clock, bus),
            midi_adapters={"stage_midi": adapter},
        )

        await interface.send_midi_adapter_test_message(
            {
                "kind": "midi",
                "name": "stage_midi",
                "status": 0xB0,
                "data": [1, 64],
            }
        )
        return send_mock

    send_mock = asyncio.run(scenario())

    send_mock.assert_awaited_once_with(0xB0, (1, 64))


def test_send_midi_adapter_test_message_accepts_program_change() -> None:
    async def scenario() -> AsyncMock:
        bus = EventBus()
        adapter = MidiAdapter(
            name="stage_midi",
            config=AdapterConfig(
                enabled=True,
                kind="midi",
                options={"output_port": "Stage MIDI Out"},
            ),
            bus=bus,
        )
        adapter.running = True
        send_mock = AsyncMock()
        adapter.send_test_message = send_mock

        interface = WebInterface(
            parse_config({"adapters": {}}),
            bus,
            ClockBpmTracker(),
            MasterClock(parse_config({"adapters": {}}).master_clock, bus),
            midi_adapters={"stage_midi": adapter},
        )

        await interface.send_midi_adapter_test_message(
            {
                "kind": "midi",
                "name": "stage_midi",
                "status": 0xCA,
                "data": [1],
            }
        )
        return send_mock

    send_mock = asyncio.run(scenario())

    send_mock.assert_awaited_once_with(0xCA, (1,))


def test_send_wing_native_adapter_test_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> AsyncMock:
        bus = EventBus()
        adapter = WingNativeAdapter(
            name="wing_native",
            config=AdapterConfig(
                enabled=True,
                kind="wing_native",
                options={"remote_host": "192.168.1.10", "native_port": 2222},
            ),
            bus=bus,
        )
        adapter.running = True
        send_mock = AsyncMock()
        monkeypatch.setattr(adapter, "send_test_message", send_mock)

        interface = WebInterface(
            parse_config({"adapters": {}}),
            bus,
            ClockBpmTracker(),
            MasterClock(parse_config({"adapters": {}}).master_clock, bus),
            wing_native_adapters={"wing_native": adapter},
        )

        await interface.send_wing_native_adapter_test_message(
            {
                "name": "wing_native",
                "address": "/ch/1/fdr",
                "value": 0.25,
            }
        )
        return send_mock

    send_mock = asyncio.run(scenario())

    send_mock.assert_awaited_once_with("/ch/1/fdr", pytest.approx(0.25))


def test_send_rtp_midi_adapter_test_message_requires_running_adapter() -> None:
    config = parse_config({"adapters": {}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        rtp_midi_adapters={
            "rtp_midi": RtpMidiAdapter(
                "rtp_midi",
                AdapterConfig(enabled=True, kind="rtp_midi", options={}),
                EventBus(),
            )
        },
    )

    with pytest.raises(OSError, match="not running"):
        asyncio.run(
            interface.send_midi_adapter_test_message(
                {
                    "kind": "rtp_midi",
                    "name": "rtp_midi",
                    "status": 0xB0,
                    "data": [1, 64],
                }
            )
        )
