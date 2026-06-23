import asyncio

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, MidiMessageEvent


def test_midi_adapter_publishes_control_events_for_library_matches() -> None:
    async def scenario() -> tuple[list[ControlEvent], list[MidiMessageEvent]]:
        bus = EventBus()
        controls: list[ControlEvent] = []
        messages: list[MidiMessageEvent] = []
        bus.subscribe(ControlEvent, lambda event: controls.append(event))
        bus.subscribe(MidiMessageEvent, lambda event: messages.append(event))

        adapter = MidiAdapter(
            "xtouch_mini",
            AdapterConfig(
                enabled=True,
                kind="midi",
                options={"midi_library": "behringer_xtouch_mini"},
            ),
            bus,
        )
        adapter.running = True
        adapter._source_index = adapter._load_source_index()

        await adapter._handle_input_message(0xBA, (1, 42))
        return controls, messages

    controls, messages = asyncio.run(scenario())

    assert len(messages) == 1
    assert messages[0].status == 0xBA
    assert len(controls) == 1
    assert controls[0].source == "xtouch_mini"
    assert controls[0].control == "layer_a_encoder_1_turn"
    assert controls[0].value == 42.0


def test_midi_adapter_publishes_raw_control_without_library() -> None:
    async def scenario() -> list[ControlEvent]:
        bus = EventBus()
        controls: list[ControlEvent] = []
        bus.subscribe(ControlEvent, lambda event: controls.append(event))

        adapter = MidiAdapter(
            "usb_stage",
            AdapterConfig(enabled=True, kind="midi", options={}),
            bus,
        )
        adapter.running = True
        adapter._source_index = None

        await adapter._handle_input_message(0xB0, (7, 55))
        return controls

    controls = asyncio.run(scenario())

    assert len(controls) == 1
    assert controls[0].control == "cc_0_7"
    assert controls[0].value == 55.0
