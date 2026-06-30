import asyncio
import socket
from unittest.mock import AsyncMock

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AdapterConfig, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import OscMessageEvent
from midijuggler.master_clock import MasterClock
from midijuggler.midi.xtouch_feedback import XTouchFeedbackRefresh
from midijuggler.web.server import WebInterface

from conftest import midi_device, osc_device, xtouch_devices_config


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_send_device_test_message_resolves_osc_library_parameter() -> None:
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
                },
                "devices": [
                    osc_device(
                        "wing_desk",
                        "behringer_wing",
                        adapter="wing_foh",
                        library_kind="wing",
                    )
                ],
            }
        )
        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            osc_adapters={"wing_foh": adapter},
        )

        result = await interface.send_device_test_message(
            {
                "uid": "wing_desk",
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
    assert result["uid"] == "wing_desk"
    assert result["parameter_id"] == "ch_1_fdr"
    assert result["parameter_label"] == "Channel 1 Fader"
    assert result["address"] == "/ch/1/fdr"
    assert result["arguments"] == [pytest.approx(0.75)]
    assert output_event is not None
    assert output_event.address == "/ch/1/fdr"
    assert output_event.arguments == (pytest.approx(0.75),)


def test_send_device_test_message_accepts_datapoint_id() -> None:
    async def scenario() -> dict[str, object]:
        listen_port = _free_udp_port()
        bus = EventBus()
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
                },
                "devices": [
                    osc_device(
                        "wing_desk",
                        "behringer_wing",
                        adapter="wing_foh",
                        library_kind="wing",
                    )
                ],
            }
        )
        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            osc_adapters={"wing_foh": adapter},
        )

        result = await interface.send_device_test_message(
            {
                "uid": "wing_desk",
                "datapoint_id": "wing_desk./ch/1/fdr",
                "value": 0.75,
            }
        )
        await adapter.stop()
        return result

    result = asyncio.run(scenario())

    assert result["ok"] is True
    assert result["parameter_id"] == "ch_1_fdr"
    assert result["address"] == "/ch/1/fdr"


def test_send_device_test_message_resolves_midi_library_parameter(
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
                },
                "devices": [
                    midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                ],
            }
        )
        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            midi_adapters={"xtouch_mini": adapter},
        )

        result = await interface.send_device_test_message(
            {
                "uid": "xtouch_mini",
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


def test_send_device_test_message_caches_feedback_for_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[dict[str, float], float | None]:
        from midijuggler.datapoint.store import DataPointStore

        bus = EventBus()
        store = DataPointStore()
        config = parse_config(xtouch_devices_config(feedback_refresh_interval=1.0))
        adapter = MidiAdapter(
            name="xtouch_mini",
            config=config.adapters["xtouch_mini"],
            bus=bus,
            app_config=config,
        )
        adapter.bind_datapoint_store(store)
        adapter.running = True
        adapter._feedback_refresh = XTouchFeedbackRefresh(adapter, config)
        adapter._feedback_refresh.configure(
            config.adapters["xtouch_mini"],
            config,
            config.devices["xtouch_mini"],
            store=store,
            device_id=config.devices["xtouch_mini"].uid,
        )
        adapter._output_address = "out"
        monkeypatch.setattr(adapter, "_emit_midi_output", AsyncMock())

        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            midi_adapters={"xtouch_mini": adapter},
            datapoint_store=store,
        )

        await interface.send_device_test_message(
            {
                "uid": "xtouch_mini",
                "parameter_id": "layer_a_top_button_1_led",
                "value": 1,
            }
        )
        return dict(adapter._feedback_refresh._cache), store.float_value(
            "xtouch_mini.layer_a_top_button_1_led"
        )

    cache, stored = asyncio.run(scenario())

    assert cache["layer_a_top_button_1_led"] == 1.0
    assert stored == 1.0


def test_send_device_test_message_via_wing_native_adapter(
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

        config = parse_config(
            {
                "adapters": {
                    "wing_native": {
                        "enabled": True,
                        "type": "wing_native",
                        "remote_host": "192.168.1.10",
                        "native_port": 2222,
                    }
                },
                "devices": [
                    osc_device(
                        "wing_desk",
                        "behringer_wing",
                        adapter="wing_native",
                        library_kind="wing",
                    ),
                ],
            }
        )
        interface = WebInterface(
            config,
            bus,
            ClockBpmTracker(),
            MasterClock(config.master_clock, bus),
            wing_native_adapters={"wing_native": adapter},
        )

        await interface.send_device_test_message(
            {
                "uid": "wing_desk",
                "parameter_id": "ch_1_fdr",
                "value": 0.5,
            }
        )
        return send_mock

    send_mock = asyncio.run(scenario())

    send_mock.assert_awaited_once_with("/ch/1/fdr", pytest.approx(0.5))
