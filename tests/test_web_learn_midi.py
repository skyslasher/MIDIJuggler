import asyncio

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_select_learn_source_from_monitor_midi_message() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": True,
                    "midi_library": "behringer_xtouch_mini",
                }
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )
    interface.learn.set_enabled(True)

    asyncio.run(
        interface.apply_learn_source(
            {
                "event": {
                    "kind": "MidiMessageEvent",
                    "source": "xtouch_mini",
                    "status": 0xB0,
                    "data": [1, 64],
                    "direction": "input",
                }
            }
        )
    )

    payload = interface._status_payload()
    assert payload["learn"]["phase"] == "waiting_target"
    assert payload["learn"]["source"] == "xtouch_mini:layer_a_encoder_1_turn"
