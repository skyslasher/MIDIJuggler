import asyncio

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AdapterConfig, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import MappedEvent, MidiMessageEvent
from midijuggler.device.registry import DeviceRegistry
from midijuggler.midi.target_encode import encode_legacy_midi_target_point, encode_mapped_midi_target

from conftest import midi_device


def test_encode_legacy_cc_target_uses_one_based_channel() -> None:
    status, data = encode_legacy_midi_target_point("cc:1:64", 127.0)

    assert status == 0xB0
    assert data == (64, 127)


def test_encode_legacy_cc_datapoint_uses_one_based_channel() -> None:
    status, data = encode_legacy_midi_target_point("cc_1_64", 64.0)

    assert status == 0xB0
    assert data == (64, 64)


def test_encode_mapped_midi_target_for_xtouch_library_parameter() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                }
            },
            "devices": [
                midi_device("xtouch_mini", library="behringer_xtouch_mini"),
            ],
        }
    )
    registry = DeviceRegistry.from_config(config)

    status, data = encode_mapped_midi_target(
        config,
        registry,
        "xtouch_mini",
        "layer_a_encoder_1_led_ring",
        14.0,
    )

    assert status == 0xBB
    assert data == (1, 14)


def test_midi_adapter_send_emits_encoded_midi_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> MidiMessageEvent | None:
        config = parse_config(
            {
                "adapters": {
                    "xtouch_mini": {
                        "enabled": True,
                        "type": "midi",
                        "input_port": "X-TOUCH MINI",
                        "output_port": "X-TOUCH MINI",
                    }
                },
                "devices": [midi_device("xtouch_mini")],
            }
        )
        bus = EventBus()
        events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: events.append(event))

        adapter = MidiAdapter(
            "xtouch_mini",
            config.adapters["xtouch_mini"],
            bus,
            app_config=config,
        )
        adapter._output_address = "X-TOUCH MINI MIDI 1"
        async def capture_output(address: str, event: MidiMessageEvent) -> None:
            events.append(event)

        monkeypatch.setattr(adapter, "_emit_midi_output", capture_output)

        await adapter.send(
            MappedEvent(
                source="mapping",
                target="xtouch_mini:cc:1:64",
                value=100.0,
            )
        )
        return next((event for event in events if event.direction == "output"), None)

    output_event = asyncio.run(scenario())

    assert output_event is not None
    assert output_event.status == 0xB0
    assert output_event.data == (64, 100)
