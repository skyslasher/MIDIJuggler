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


def test_service_filters_disabled_master_clock_output_targets() -> None:
    service = MIDIJugglerService(
        parse_config(
            {
                "master_clock": {
                    "enabled": True,
                    "output_targets": ["usb_midi", "rtp_midi"],
                },
                "adapters": {
                    "usb_midi": {"enabled": True},
                    "rtp_midi": {"enabled": False},
                },
            }
        )
    )

    assert service.master_clock.config.output_targets == ["usb_midi"]


def test_service_filters_master_clock_midi_input_targets() -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(
            parse_config(
                {
                    "master_clock": {
                        "enabled": True,
                        "midi_input_targets": ["usb_stage"],
                    },
                    "adapters": {
                        "usb_midi": {"enabled": True},
                        "usb_stage": {"type": "usb_midi", "enabled": True},
                    },
                }
            )
        )
        await service._handle_midi_message(
            MidiMessageEvent(source="usb_midi", direction="input", status=MIDI_START)
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
                    "master_clock": {"enabled": True},
                    "adapters": {"usb_midi": {"enabled": True}},
                }
            )
        )
        await service._handle_midi_message(
            MidiMessageEvent(source="usb_midi", direction="input", status=MIDI_START)
        )
        return service

    service = asyncio.run(scenario())

    assert service.master_clock.running is True


def test_service_filters_master_clock_osc_input_targets() -> None:
    async def scenario() -> None:
        service = MIDIJugglerService(
            parse_config(
                {
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
