import asyncio
from unittest.mock import AsyncMock

import pytest

from midijuggler.config import AdapterConfig, parse_config
from midijuggler.midi.xtouch_feedback import (
    XTouchFeedbackRefresh,
    encoder_value_to_led_ring,
    feedback_point_ids,
    is_layer_program_change,
    paired_led_ring_point,
    parse_feedback_refresh_interval,
    uses_xtouch_feedback_refresh,
)


def test_parse_feedback_refresh_interval_accepts_tenth_steps() -> None:
    assert parse_feedback_refresh_interval(0) == 0.0
    assert parse_feedback_refresh_interval(0.1) == 0.1
    assert parse_feedback_refresh_interval(2.5) == 2.5


def test_parse_feedback_refresh_interval_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="0.1 second steps"):
        parse_feedback_refresh_interval(0.15)
    with pytest.raises(ValueError, match=">= 0"):
        parse_feedback_refresh_interval(-0.1)
    with pytest.raises(ValueError, match="<= 60"):
        parse_feedback_refresh_interval(60.1)


def test_uses_xtouch_feedback_refresh_only_for_xtouch_library() -> None:
    xtouch = AdapterConfig(
        enabled=True,
        options={"midi_library": "behringer_xtouch_mini"},
        kind="midi",
    )
    generic = AdapterConfig(enabled=True, options={}, kind="midi")

    assert uses_xtouch_feedback_refresh(xtouch) is True
    assert uses_xtouch_feedback_refresh(generic) is False


def test_feedback_point_ids_lists_xtouch_feedback_targets() -> None:
    config = AdapterConfig(
        enabled=True,
        options={"midi_library": "behringer_xtouch_mini"},
        kind="midi",
    )

    points = feedback_point_ids(config)

    assert "layer_a_top_button_1_led" in points
    assert "layer_a_encoder_1_led_ring" in points
    assert "layer_a_encoder_1_value" in points
    assert all(
        point.endswith("_led")
        or point.endswith("_led_ring")
        or point.endswith("_value")
        for point in points
    )


def test_paired_led_ring_point_for_encoder_value() -> None:
    assert paired_led_ring_point("layer_a_encoder_1_value") == "layer_a_encoder_1_led_ring"
    assert paired_led_ring_point("layer_a_top_button_1_led") is None


def test_encoder_value_to_led_ring_scales_positions() -> None:
    assert encoder_value_to_led_ring(0.0) == 0.0
    assert encoder_value_to_led_ring(127.0) == 13.0
    assert encoder_value_to_led_ring(63.5) == 6.0


def test_remember_mirrors_encoder_value_to_led_ring() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                }
            }
        }
    )
    adapter = AsyncMock()
    adapter.name = "xtouch_mini"
    adapter.running = True
    refresh = XTouchFeedbackRefresh(adapter, config)
    refresh.configure(config.adapters["xtouch_mini"], config)

    refresh.remember("layer_a_encoder_1_value", 127.0)

    assert refresh._cache == {
        "layer_a_encoder_1_value": 127.0,
        "layer_a_encoder_1_led_ring": 13.0,
    }


def test_is_layer_program_change_detects_xtouch_layer_buttons() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                }
            }
        }
    )
    layer_a_status = 0xC0 | (11 - 1)
    layer_b_status = 0xC0 | (11 - 1)

    assert is_layer_program_change(config.adapters["xtouch_mini"], layer_a_status, (0,)) is True
    assert is_layer_program_change(config.adapters["xtouch_mini"], layer_b_status, (1,)) is True
    assert is_layer_program_change(config.adapters["xtouch_mini"], layer_a_status, (2,)) is False


def test_remember_only_caches_feedback_targets() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                }
            }
        }
    )
    adapter = AsyncMock()
    adapter.name = "xtouch_mini"
    adapter.running = True
    refresh = XTouchFeedbackRefresh(adapter, config)
    refresh.configure(config.adapters["xtouch_mini"], config)

    refresh.remember("layer_a_top_button_1_led", 1.0)
    refresh.remember("layer_a_encoder_1", 0.5)

    assert refresh._cache == {"layer_a_top_button_1_led": 1.0}


def test_refresh_loop_resends_cached_values() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                    "feedback_refresh_interval": 0.1,
                }
            }
        }
    )
    adapter = AsyncMock()
    adapter.name = "xtouch_mini"
    adapter.running = True
    adapter.send_feedback_target = AsyncMock()
    refresh = XTouchFeedbackRefresh(adapter, config)
    refresh.configure(config.adapters["xtouch_mini"], config)
    refresh.remember("layer_a_top_button_1_led", 1.0)

    async def scenario() -> None:
        await refresh.start(config.adapters["xtouch_mini"])
        await asyncio.sleep(0.25)
        await refresh.stop()

    asyncio.run(scenario())

    assert adapter.send_feedback_target.await_count >= 1
    adapter.send_feedback_target.assert_any_await("layer_a_top_button_1_led", 1.0)


def test_send_feedback_target_marks_monitor_events_as_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from midijuggler.adapters.midi import MidiAdapter
    from midijuggler.eventbus import EventBus
    from midijuggler.events import MidiMessageEvent

    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                }
            }
        }
    )
    adapter = MidiAdapter(
        "xtouch_mini",
        config.adapters["xtouch_mini"],
        EventBus(),
        app_config=config,
    )
    adapter._output_address = "out"
    published: list[MidiMessageEvent] = []

    async def capture_publish(event: MidiMessageEvent) -> None:
        published.append(event)

    monkeypatch.setattr(adapter.bus, "publish", capture_publish)
    monkeypatch.setattr(
        "midijuggler.adapters.midi.send_midi_message_to_port",
        AsyncMock(),
    )

    async def scenario() -> None:
        await adapter.send_feedback_target("layer_a_top_button_1_led", 1.0)

    asyncio.run(scenario())

    assert len(published) == 1
    assert published[0].feedback_refresh is True


def test_midi_adapter_remembers_feedback_on_send(monkeypatch: pytest.MonkeyPatch) -> None:
    from midijuggler.adapters.midi import MidiAdapter
    from midijuggler.eventbus import EventBus
    from midijuggler.events import MappedEvent

    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                    "feedback_refresh_interval": 0.1,
                }
            }
        }
    )
    adapter = MidiAdapter(
        "xtouch_mini",
        config.adapters["xtouch_mini"],
        EventBus(),
        app_config=config,
    )
    monkeypatch.setattr(adapter, "_emit_midi_output", AsyncMock())
    adapter._output_address = "out"

    async def scenario() -> None:
        adapter._feedback_refresh = XTouchFeedbackRefresh(adapter, config)
        adapter._feedback_refresh.configure(config.adapters["xtouch_mini"], config)
        await adapter.send(
            MappedEvent(
                source="mapping",
                target="xtouch_mini:layer_a_top_button_1_led",
                value=1.0,
            )
        )

    asyncio.run(scenario())

    assert adapter._feedback_refresh is not None
    assert adapter._feedback_refresh._cache["layer_a_top_button_1_led"] == 1.0


def test_send_test_message_remembers_feedback_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    from midijuggler.adapters.midi import MidiAdapter
    from midijuggler.eventbus import EventBus

    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                    "feedback_refresh_interval": 0.1,
                }
            }
        }
    )
    adapter = MidiAdapter(
        "xtouch_mini",
        config.adapters["xtouch_mini"],
        EventBus(),
        app_config=config,
    )
    monkeypatch.setattr(adapter, "_emit_midi_output", AsyncMock())
    adapter._output_address = "out"
    adapter._feedback_refresh = XTouchFeedbackRefresh(adapter, config)
    adapter._feedback_refresh.configure(config.adapters["xtouch_mini"], config)

    async def scenario() -> None:
        await adapter.send_test_message(
            0x9A,
            (8, 127),
            feedback_point="layer_a_top_button_1_led",
            feedback_value=1.0,
        )

    asyncio.run(scenario())

    assert adapter._feedback_refresh._cache["layer_a_top_button_1_led"] == 1.0


def test_layer_program_change_triggers_feedback_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    from midijuggler.adapters.midi import MidiAdapter
    from midijuggler.eventbus import EventBus

    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "enabled": True,
                    "type": "midi",
                    "midi_library": "behringer_xtouch_mini",
                    "feedback_refresh_interval": 1.0,
                }
            }
        }
    )
    adapter = MidiAdapter(
        "xtouch_mini",
        config.adapters["xtouch_mini"],
        EventBus(),
        app_config=config,
    )
    adapter._source_index = None
    refresh = XTouchFeedbackRefresh(adapter, config)
    refresh.configure(config.adapters["xtouch_mini"], config)
    refresh.remember("layer_a_encoder_1_value", 127.0)
    adapter._feedback_refresh = refresh
    adapter.send_feedback_target = AsyncMock()

    async def scenario() -> None:
        await adapter._handle_input_message(0xC0 | (11 - 1), (1,))

    asyncio.run(scenario())

    assert adapter.send_feedback_target.await_count >= 2
