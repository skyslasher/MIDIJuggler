import asyncio
import socket
from unittest.mock import AsyncMock

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AdapterConfig, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import OscMessageEvent
from midijuggler.master_clock import MasterClock
from midijuggler.midi.xtouch_feedback import XTouchFeedbackRefresh
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


def test_send_osc_adapter_test_message_resolves_library_parameter() -> None:
    async def scenario() -> tuple[dict[str, object], OscMessageEvent | None]:
        listen_port = _free_udp_port()
        bus = EventBus()
        events: list[OscMessageEvent] = []
        bus.subscribe(OscMessageEvent, lambda event: events.append(event))

        adapter_config = AdapterConfig(
            enabled=True,
            kind="osc",
            options={
                "osc_port": listen_port,
                "listen_host": "127.0.0.1",
                "remote_host": "127.0.0.1",
                "osc_library": "behringer_wing",
            },
        )
        adapter = OscAdapter(
            name="wing_foh",
            config=adapter_config,
            bus=bus,
        )
        await adapter.start()

        config = parse_config(
            {
                "adapters": {
                    "wing_foh": {
                        "enabled": True,
                        "type": "osc",
                        **adapter_config.options,
                    }
                }
            }
        )
        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            osc_adapters={"wing_foh": adapter},
        )

        result = await interface.send_osc_adapter_test_message(
            {
                "name": "wing_foh",
                "parameter_id": "ch_1_fdr",
                "value": 0.75,
            }
        )
        await adapter.stop()
        output_event = next(
            (event for event in events if event.direction == "output"),
            None,
        )
        return result, output_event

    result, output_event = asyncio.run(scenario())

    assert result["ok"] is True
    assert result["parameter_id"] == "ch_1_fdr"
    assert result["parameter_label"] == "Channel 1 Fader"
    assert result["address"] == "/ch/1/fdr"
    assert result["arguments"] == [pytest.approx(0.75)]
    assert output_event is not None
    assert output_event.address == "/ch/1/fdr"
    assert output_event.arguments == (pytest.approx(0.75),)


def test_send_midi_adapter_test_message_resolves_library_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[dict[str, object], AsyncMock]:
        bus = EventBus()
        adapter = MidiAdapter(
            name="xtouch_mini",
            config=AdapterConfig(
                enabled=True,
                kind="midi",
                options={
                    "output_port": "X-Touch Mini",
                    "midi_library": "behringer_xtouch_mini",
                },
            ),
            bus=bus,
        )
        adapter.running = True
        send_mock = AsyncMock()
        monkeypatch.setattr(adapter, "send_test_message", send_mock)

        config = parse_config(
            {
                "adapters": {
                    "xtouch_mini": {
                        "enabled": True,
                        "type": "midi",
                        "output_port": "X-Touch Mini",
                        "midi_library": "behringer_xtouch_mini",
                    }
                }
            }
        )
        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            midi_adapters={"xtouch_mini": adapter},
        )

        result = await interface.send_midi_adapter_test_message(
            {
                "kind": "midi",
                "name": "xtouch_mini",
                "parameter_id": "layer_a_top_button_1_led",
                "value": 1,
            }
        )
        return result, send_mock

    result, send_mock = asyncio.run(scenario())

    assert result["ok"] is True
    assert result["parameter_id"] == "layer_a_top_button_1_led"
    assert result["parameter_label"] == "Layer A Top Button 1 LED"
    assert result["status"] == 0x9A
    assert result["data"] == [8, 127]
    send_mock.assert_awaited_once_with(
        0x9A,
        (8, 127),
        feedback_point="layer_a_top_button_1_led",
        feedback_value=1.0,
    )


def test_send_midi_adapter_test_message_caches_feedback_for_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> dict[str, float]:
        bus = EventBus()
        config = parse_config(
            {
                "adapters": {
                    "xtouch_mini": {
                        "enabled": True,
                        "type": "midi",
                        "output_port": "X-Touch Mini",
                        "midi_library": "behringer_xtouch_mini",
                        "feedback_refresh_interval": 1.0,
                    }
                }
            }
        )
        adapter = MidiAdapter(
            name="xtouch_mini",
            config=config.adapters["xtouch_mini"],
            bus=bus,
            app_config=config,
        )
        adapter.running = True
        adapter._feedback_refresh = XTouchFeedbackRefresh(adapter, config)
        adapter._feedback_refresh.configure(config.adapters["xtouch_mini"], config)
        monkeypatch.setattr(adapter, "_resolve_output_address", lambda: "out")
        monkeypatch.setattr(adapter, "_emit_midi_output", AsyncMock())

        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            midi_adapters={"xtouch_mini": adapter},
        )

        await interface.send_midi_adapter_test_message(
            {
                "kind": "midi",
                "name": "xtouch_mini",
                "parameter_id": "layer_a_top_button_1_led",
                "value": 1,
            }
        )
        return dict(adapter._feedback_refresh._cache)

    cache = asyncio.run(scenario())

    assert cache["layer_a_top_button_1_led"] == 1.0


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

    send_mock.assert_awaited_once_with(0xB0, (1, 64), feedback_point=None, feedback_value=None)


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
