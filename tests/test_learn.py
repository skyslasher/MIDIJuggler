from midijuggler.config import parse_config
from midijuggler.learn import (
    LearnController,
    LearnSource,
    resolve_monitor_source,
    upsert_connection,
    upsert_mapping_rule,
)
from midijuggler.datapoint.types import ModifierKind
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


def test_resolve_monitor_source_from_hid_event() -> None:
    config = parse_config({"adapters": {}})
    source = resolve_monitor_source(
        config,
        {
            "kind": "HidEvent",
            "source": "gamepad",
            "control": "btn_a",
            "code": "BTN_A",
            "value": 1.0,
            "initial": False,
        },
    )

    assert source.key == "gamepad:btn_a"


def test_resolve_monitor_source_from_hid_learn_event() -> None:
    config = parse_config({"adapters": {}})
    source = resolve_monitor_source(
        config,
        {
            "kind": "HidLearnEvent",
            "source": "keyboard",
            "code": "KEY_A",
            "suggested_control": "key_a",
            "value": 1.0,
        },
    )

    assert source.key == "keyboard:key_a"


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


def test_select_source_datapoint_sets_waiting_target() -> None:
    controller = LearnController()
    controller.set_enabled(True)

    state = controller.select_source_datapoint("gpio.pin17")

    assert state.phase == "waiting_target"
    assert state.source_datapoint == "gpio.pin17"


def test_build_connection_uses_modifier_and_ranges() -> None:
    controller = LearnController()
    connection = controller.build_connection(
        source_datapoint="gpio.pin17",
        target_datapoint="x32_foh./ch/01/mix/01/level",
        modifier=ModifierKind.PASSTHROUGH,
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=1.0,
    )

    assert connection.source == "gpio.pin17"
    assert connection.modifier == ModifierKind.PASSTHROUGH


def test_upsert_connection_replaces_same_source() -> None:
    from midijuggler.datapoint.types import ConnectionSpec

    existing = ConnectionSpec(
        id="old",
        source="gpio.pin17",
        target="x32_foh./ch/01/mix/02/level",
    )
    replacement = ConnectionSpec(
        id="new",
        source="gpio.pin17",
        target="x32_foh./ch/01/mix/01/level",
    )

    updated = upsert_connection([existing], replacement)

    assert len(updated) == 1
    assert updated[0].id == "new"


def test_reverse_connection_maps_encoder_turn_to_value() -> None:
    from midijuggler.datapoint.types import ConnectionSpec
    from midijuggler.learn import reverse_connection, suggest_feedback_target

    forward = ConnectionSpec(
        id="encoder-to-fader",
        source="xtouch_mini.layer_a_encoder_1_turn",
        target="x32_foh./ch/01/mix/fader",
        input_min=1.0,
        input_max=127.0,
        output_min=0.0,
        output_max=1.0,
    )

    assert suggest_feedback_target(forward.source, forward.target) == (
        "xtouch_mini.layer_a_encoder_1_value"
    )

    feedback = reverse_connection(forward)
    assert feedback.source == "x32_foh./ch/01/mix/fader"
    assert feedback.target == "xtouch_mini.layer_a_encoder_1_value"
    assert feedback.input_min == 0.0
    assert feedback.input_max == 1.0
    assert feedback.output_min == 1.0
    assert feedback.output_max == 127.0


def test_reverse_connection_preserves_forward_input_ranges_for_feedback() -> None:
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.datapoint.types import (
        ConnectionSpec,
        DataPointDirection,
        DataPointId,
        DataPointSpec,
        ValueType,
    )
    from midijuggler.learn import reverse_connection

    store = DataPointStore()
    store.register(
        DataPointSpec(
            id=DataPointId("xtouch_mini", "layer_a_encoder_1_value"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.OUTPUT,
            value_min=0.0,
            value_max=127.0,
            protocol="midi",
        )
    )
    forward = ConnectionSpec(
        id="encoder-to-fader",
        source="xtouch_mini.layer_a_encoder_1_turn",
        target="x32_foh./ch/01/mix/fader",
        input_min=1.0,
        input_max=127.0,
        output_min=0.0,
        output_max=1.0,
    )

    feedback = reverse_connection(forward, store)

    assert feedback.output_min == 1.0
    assert feedback.output_max == 127.0


def test_reverse_connection_swaps_customized_ranges() -> None:
    from midijuggler.datapoint.types import ConnectionSpec
    from midijuggler.learn import reverse_connection

    forward = ConnectionSpec(
        id="fader-to-wing",
        source="xtouch_mini.layer_a_fader_1",
        target="wing_native_foh./ch/1/fader",
        input_min=0.0,
        input_max=63.0,
        output_min=-90.0,
        output_max=10.0,
    )

    feedback = reverse_connection(forward)

    assert feedback.input_min == -90.0
    assert feedback.input_max == 10.0
    assert feedback.output_min == 0.0
    assert feedback.output_max == 63.0
