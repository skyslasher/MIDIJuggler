import asyncio
import logging

import pytest

from midijuggler.config import parse_config
from midijuggler.events import MidiMessageEvent, OscMessageEvent
from midijuggler.master_clock import MIDI_START, MIDI_STOP, MIDI_TIMING_CLOCK
from midijuggler.service import MIDIJugglerService


def test_missing_midi_timing_clock_target_does_not_warn(caplog) -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(parse_config({}))
        with caplog.at_level(logging.WARNING, logger="midijuggler.service"):
            await service._handle_midi_message(
                MidiMessageEvent(
                    source="master_clock",
                    direction="output",
                    target="rtp_midi",
                    status=MIDI_TIMING_CLOCK,
                )
            )

    asyncio.run(scenario())

    assert "no enabled adapter for MIDI target" not in caplog.text


def test_missing_non_clock_midi_target_still_warns(caplog) -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(parse_config({}))
        with caplog.at_level(logging.WARNING, logger="midijuggler.service"):
            await service._handle_midi_message(
                MidiMessageEvent(
                    source="master_clock",
                    direction="output",
                    target="rtp_midi",
                    status=MIDI_STOP,
                )
            )

    asyncio.run(scenario())

    assert "no enabled adapter for MIDI target rtp_midi" in caplog.text


def test_handle_midi_message_ignores_adapter_originated_output() -> None:
    async def scenario() -> int:
        service = MIDIJugglerService(
            parse_config(
                {
                    "adapters": {
                        "xtouch_mini": {
                            "enabled": True,
                            "type": "midi",
                            "output_port": "X-TOUCH MINI",
                        }
                    }
                }
            )
        )
        adapter = next(item for item in service.adapters if item.name == "xtouch_mini")
        calls = 0

        async def track_send(_event: MidiMessageEvent) -> None:
            nonlocal calls
            calls += 1

        adapter.send_midi_message = track_send  # type: ignore[method-assign]
        await service._handle_midi_message(
            MidiMessageEvent(
                source="xtouch_mini",
                direction="output",
                target="xtouch_mini:layer_a_top_button_1_led",
                status=0x9A,
                data=(8, 127),
            )
        )
        return calls

    assert asyncio.run(scenario()) == 0


def test_handle_midi_message_routes_master_clock_output() -> None:
    async def scenario() -> int:
        service = MIDIJugglerService(
            parse_config({"adapters": {"midi": {"enabled": True}}})
        )
        adapter = next(item for item in service.adapters if item.name == "midi")
        calls = 0

        async def track_send(_event: MidiMessageEvent) -> None:
            nonlocal calls
            calls += 1

        adapter.send_midi_message = track_send  # type: ignore[method-assign]
        await service._handle_midi_message(
            MidiMessageEvent(
                source="master_clock",
                direction="output",
                target="midi",
                status=MIDI_STOP,
            )
        )
        return calls

    assert asyncio.run(scenario()) == 1


def test_emit_midi_output_does_not_recurse_through_service_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> int:
        from midijuggler.midi.output import send_midi_message_to_port

        config = parse_config(
            {
                "adapters": {
                    "xtouch_mini": {
                        "enabled": True,
                        "type": "midi",
                        "output_port": "X-TOUCH MINI",
                    }
                }
            }
        )
        service = MIDIJugglerService(config)
        adapter = next(item for item in service.adapters if item.name == "xtouch_mini")
        adapter._output_address = "20:0"
        send_calls = 0

        async def track_port_send(
            _address: str,
            _status: int,
            _data: tuple[int, ...],
        ) -> None:
            nonlocal send_calls
            send_calls += 1

        monkeypatch.setattr(
            "midijuggler.adapters.midi.send_midi_message_to_port",
            track_port_send,
        )
        await adapter._emit_midi_output(
            "20:0",
            MidiMessageEvent(
                source="xtouch_mini",
                direction="output",
                target="xtouch_mini:layer_a_top_button_1_led",
                status=0x9A,
                data=(8, 127),
            ),
        )
        return send_calls

    assert asyncio.run(scenario()) == 1


from conftest import midi_device


def test_service_filters_disabled_master_clock_output_targets() -> None:
    service = MIDIJugglerService(
        parse_config(
            {
                "master_clock": {
                    "enabled": True,
                    "output_targets": ["midi", "rtp_midi"],
                },
                "adapters": {
                    "midi": {
                        "enabled": True,
                        "output_port": "MIDIJuggler Out",
                    },
                    "rtp_midi": {"enabled": False},
                },
                "devices": [
                    midi_device("midi", adapter="midi"),
                    midi_device("rtp_midi", adapter="rtp_midi"),
                ],
            }
        )
    )

    assert service.master_clock.config.output_targets == ["midi"]


def test_service_filters_master_clock_midi_input_targets() -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {"datapoint_routing": False},
                    "master_clock": {
                        "enabled": True,
                        "midi_input_targets": ["usb_stage"],
                    },
                    "adapters": {
                        "midi": {"enabled": True},
                        "usb_stage": {"type": "midi", "enabled": True},
                    },
                }
            )
        )
        await service._handle_midi_message(
            MidiMessageEvent(source="midi", direction="input", status=MIDI_START)
        )
        await service._handle_midi_message(
            MidiMessageEvent(source="usb_stage", direction="input", status=MIDI_STOP)
        )
        return service

    service = asyncio.run(scenario())

    assert service.master_clock.running is False


def test_service_accepts_all_enabled_midi_inputs_when_unconfigured() -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {"datapoint_routing": False},
                    "master_clock": {"enabled": True},
                    "adapters": {"midi": {"enabled": True}},
                }
            )
        )
        await service._handle_midi_message(
            MidiMessageEvent(source="midi", direction="input", status=MIDI_START)
        )
        return service

    service = asyncio.run(scenario())

    assert service.master_clock.running is True


def test_service_filters_master_clock_osc_input_targets() -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {"datapoint_routing": False},
                    "master_clock": {
                        "enabled": True,
                        "osc_input_targets": ["osc_pedalboard"],
                    },
                    "adapters": {
                        "osc": {"enabled": True},
                        "osc_pedalboard": {
                            "type": "osc",
                            "enabled": True,
                            "listen_port": 9001,
                        },
                    },
                }
            )
        )
        await service._handle_osc_message(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(140.0,),
            )
        )
        await service._handle_osc_message(
            OscMessageEvent(
                source="osc_pedalboard",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(150.0,),
            )
        )
        return service

    service = asyncio.run(scenario())

    assert service.master_clock.bpm == pytest.approx(150.0)


def test_service_ignores_echo_suppressed_master_clock_osc() -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {"datapoint_routing": False},
                    "master_clock": {"enabled": True},
                    "adapters": {"osc": {"enabled": True}},
                }
            )
        )
        await service._handle_osc_message(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(200.0,),
                echo_suppressed=True,
            )
        )
        return service

    service = asyncio.run(scenario())

    assert service.master_clock.bpm == pytest.approx(120.0)


def _patch_adapters_noop_start(monkeypatch: pytest.MonkeyPatch, service: MIDIJugglerService) -> None:
    async def fake_start(adapter) -> None:
        adapter.running = True

    async def fake_stop(adapter) -> None:
        adapter.running = False

    for adapter in service.adapters:
        monkeypatch.setattr(adapter, "start", lambda adapter=adapter: fake_start(adapter))
        monkeypatch.setattr(adapter, "stop", lambda adapter=adapter: fake_stop(adapter))


async def _start_service_for_datapoint_tests(service: MIDIJugglerService) -> None:
    await service.rtp_midi_manager.start()
    await service.osc_desk_tracker.start()
    await service.module_registry.start_all()
    await service.web.refresh_all_device_datapoints()
    if service.web.modifier_graph is not None:
        await service.web.modifier_graph.replay_subscribed_sources_from_store()
    service.event_bridge.attach()
    await service.master_clock.start()


def test_service_routes_master_clock_osc_to_store_with_datapoint_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> MIDIJugglerService:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {
                        "datapoint_routing": True,
                        "suppressed_inferred_device_adapters": ["osc"],
                    },
                    "master_clock": {"enabled": True, "bpm": 122.0},
                    "adapters": {"osc": {"enabled": True, "type": "osc", "listen_port": 9000}},
                    "devices": [],
                    "rotary_display": {"enabled": True},
                }
            )
        )
        _patch_adapters_noop_start(monkeypatch, service)
        await _start_service_for_datapoint_tests(service)
        await service._handle_osc_message(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(115.0,),
            )
        )
        return service

    service = asyncio.run(scenario())
    assert service.master_clock.bpm == pytest.approx(115.0)
    assert service.datapoint_store.float_value("clock.bpm_set") == pytest.approx(115.0)


def test_service_routes_master_clock_osc_without_rotary_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> MIDIJugglerService:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {"datapoint_routing": True},
                    "master_clock": {"enabled": True, "bpm": 122.0},
                    "adapters": {"osc": {"enabled": True, "type": "osc", "listen_port": 9000}},
                    "devices": [],
                    "rotary_display": {"enabled": True},
                }
            )
        )
        _patch_adapters_noop_start(monkeypatch, service)
        await _start_service_for_datapoint_tests(service)
        await service._handle_osc_message(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(115.0,),
            )
        )
        return service

    service = asyncio.run(scenario())
    assert service.master_clock.bpm == pytest.approx(115.0)


def test_service_routes_master_clock_osc_when_bridge_maps_to_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conftest import osc_device

    async def scenario() -> tuple[MIDIJugglerService, float]:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {"datapoint_routing": True},
                    "master_clock": {"enabled": True, "bpm": 122.0},
                    "adapters": {"osc": {"enabled": True, "type": "osc", "listen_port": 9000}},
                    "devices": [osc_device("rotary_encoder", "rotary_display", adapter="osc")],
                    "rotary_display": {"enabled": True},
                }
            )
        )
        _patch_adapters_noop_start(monkeypatch, service)
        await _start_service_for_datapoint_tests(service)
        await service._handle_osc_message(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(115.0,),
            )
        )
        await service.master_clock.flush_bpm_notifications()
        direct_bpm = service.master_clock.bpm
        return service, direct_bpm

    service, direct_bpm = asyncio.run(scenario())
    assert direct_bpm == pytest.approx(115.0)
    assert service.datapoint_store.float_value("clock.bpm") == pytest.approx(115.0)


def test_service_routes_master_clock_osc_with_empty_input_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> MIDIJugglerService:
        service = MIDIJugglerService(
            parse_config(
                {
                    "runtime": {
                        "datapoint_routing": True,
                        "suppressed_inferred_device_adapters": ["osc"],
                    },
                    "master_clock": {
                        "enabled": True,
                        "bpm": 122.0,
                        "osc_input_targets": [],
                    },
                    "adapters": {"osc": {"enabled": True, "type": "osc", "listen_port": 9000}},
                    "devices": [],
                    "rotary_display": {"enabled": True},
                }
            )
        )
        _patch_adapters_noop_start(monkeypatch, service)
        await _start_service_for_datapoint_tests(service)
        await service._handle_osc_message(
            OscMessageEvent(
                source="osc",
                direction="input",
                address="/midijuggler/clock/bpm",
                arguments=(115.0,),
            )
        )
        await service.master_clock.flush_bpm_notifications()
        return service

    service = asyncio.run(scenario())
    assert service.master_clock.bpm == pytest.approx(115.0)


def test_service_writes_master_clock_alsa_config(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [master_clock]
        click_audio_device = "plughw:1,0"
        """,
        encoding="utf-8",
    )

    MIDIJugglerService(parse_config({"master_clock": {"click_audio_device": "plughw:1,0"}}), config_path=config_path)

    asoundrc = tmp_path / "asoundrc"
    assert asoundrc.exists()
    assert 'pcm "hw:1,0"' in asoundrc.read_text(encoding="utf-8")
