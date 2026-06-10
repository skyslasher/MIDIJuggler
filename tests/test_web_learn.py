import asyncio
from pathlib import Path

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent
from midijuggler.mapping import MappingEngine
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_learn_capture_updates_status_payload() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": True,
                    "midi_library": "behringer_xtouch_mini",
                },
                "x32_foh": {
                    "type": "osc",
                    "enabled": True,
                    "osc_library": "behringer_x32",
                },
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        mapping_engine=MappingEngine(config.mappings),
    )
    interface.learn.set_enabled(True)

    asyncio.run(
        interface._handle_learn_control(
            ControlEvent(source="xtouch_mini", control="layer_a_fader", value=12.0)
        )
    )

    payload = interface._status_payload()
    assert payload["learn"]["phase"] == "waiting_target"
    assert payload["learn"]["source"] == "xtouch_mini:layer_a_fader"
    assert payload["osc_instances"] == [
        {"name": "x32_foh", "osc_library": "behringer_x32"}
    ]


def test_apply_learn_mapping_persists_and_updates_engine(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

[adapters.xtouch_mini]
type = "midi"
enabled = true
midi_library = "behringer_xtouch_mini"

[adapters.x32_foh]
type = "osc"
enabled = true
osc_library = "behringer_x32"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    mapping_engine = MappingEngine(config.mappings)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        mapping_engine=mapping_engine,
        config_path=config_path,
    )
    interface.learn.set_enabled(True)
    interface.learn.capture(
        ControlEvent(source="xtouch_mini", control="layer_a_fader", value=12.0)
    )

    result = asyncio.run(
        interface.apply_learn_mapping(
            {
                "target_adapter": "x32_foh",
                "parameter_id": "ch_01_bus_01_send",
            }
        )
    )

    assert result["persisted"] is True
    assert result["created_mapping"]["target"] == "x32_foh:/ch/01/mix/01/level"
    assert len(mapping_engine.rules) == 1
    assert interface.learn.state.phase == "waiting_source"

    reloaded = load_config(config_path)
    assert reloaded.mappings[0].source == "xtouch_mini:layer_a_fader"
