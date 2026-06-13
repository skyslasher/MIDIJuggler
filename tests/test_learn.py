from midijuggler.config import parse_config
from midijuggler.learn import (
    LearnController,
    LearnSource,
    resolve_monitor_source,
    upsert_mapping_rule,
)
from midijuggler.mapping import MappingRule


def test_learn_controller_selects_control_source() -> None:
    controller = LearnController()
    controller.set_enabled(True)

    state = controller.select_source(
        LearnSource(adapter="xtouch_mini", control="layer_a_fader")
    )

    assert state.phase == "waiting_target"
    assert state.source is not None
    assert state.source.key == "xtouch_mini:layer_a_fader"


def test_resolve_monitor_source_from_gpio_event() -> None:
    config = parse_config({"adapters": {}})
    source = resolve_monitor_source(
        config,
        {
            "kind": "GpioEvent",
            "source": "gpio",
            "pin": 17,
            "control": "pin17",
            "value": 1.0,
            "initial": False,
        },
    )

    assert source.key == "gpio:pin17"


def test_resolve_monitor_source_from_control_event() -> None:
    config = parse_config({"adapters": {}})
    source = resolve_monitor_source(
        config,
        {
            "kind": "ControlEvent",
            "source": "gpio",
            "control": "pin17",
        },
    )

    assert source.key == "gpio:pin17"


def test_resolve_monitor_source_from_midi_message() -> None:
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
    source = resolve_monitor_source(
        config,
        {
            "kind": "MidiMessageEvent",
            "source": "xtouch_mini",
            "status": 0xBA,
            "data": [1, 64],
            "direction": "input",
        },
    )

    assert source.key == "xtouch_mini:layer_a_encoder_1_turn"


def test_build_mapping_uses_library_ranges() -> None:
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
    controller = LearnController()
    controller.set_enabled(True)
    controller.select_source(
        resolve_monitor_source(
            config,
            {
                "kind": "ControlEvent",
                "source": "xtouch_mini",
                "control": "layer_a_fader",
            },
        )
    )
    assert controller.state.source is not None

    rule = controller.build_mapping(
        config,
        source=controller.state.source,
        target_adapter="x32_foh",
        target_parameter_id="ch_01_bus_01_send",
    )

    assert rule.source == "xtouch_mini:layer_a_fader"
    assert rule.target == "x32_foh:/ch/01/mix/01/level"
    assert rule.input_min == 0.0
    assert rule.input_max == 127.0
    assert rule.output_min == 0.0
    assert rule.output_max == 1.0


def test_upsert_mapping_rule_replaces_same_source() -> None:
    existing = MappingRule(
        id="old",
        source="xtouch_mini:layer_a_fader",
        target="x32_foh:/ch/01/mix/02/level",
    )
    replacement = MappingRule(
        id="new",
        source="xtouch_mini:layer_a_fader",
        target="x32_foh:/ch/01/mix/01/level",
    )

    updated = upsert_mapping_rule([existing], replacement)

    assert len(updated) == 1
    assert updated[0].id == "new"
