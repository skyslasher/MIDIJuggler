import asyncio
import logging

from midijuggler.config import parse_config
from midijuggler.events import MidiMessageEvent
from midijuggler.master_clock import MIDI_STOP, MIDI_TIMING_CLOCK
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
