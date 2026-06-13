import asyncio

import pytest

from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AdapterConfig, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import float_value
from midijuggler.eventbus import EventBus
from midijuggler.events import MidiMessageEvent
from midijuggler.modules.io.midi import MidiIOModule


def test_midi_io_module_sends_connection_targets_without_library(
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
                "mappings": [
                    {
                        "id": "gpio-to-xtouch-cc",
                        "source": "gpio:pin17",
                        "target": "xtouch_mini:cc:1:64",
                    }
                ],
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
        monkeypatch.setattr(
            adapter,
            "send_midi_message",
            lambda event: events.append(event),
        )

        store = DataPointStore()
        module = MidiIOModule(adapter, store, config)
        await module.start()
        await store.write(float_value("xtouch_mini.cc_1_64", 80.0))
        return next((event for event in events if event.direction == "output"), None)

    output_event = asyncio.run(scenario())

    assert output_event is not None
    assert output_event.status == 0xB0
    assert output_event.data == (64, 80)
