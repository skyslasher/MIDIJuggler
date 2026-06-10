import asyncio

import pytest

from midijuggler.config import MasterClockConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ClickEvent, ControlEvent, MidiMessageEvent, OscMessageEvent
from midijuggler.master_clock import (
    MIDI_START,
    MIDI_STOP,
    MIDI_TIMING_CLOCK,
    MasterClock,
    bpm_to_parameters,
)


class FakeClickPlayer:
    def __init__(self) -> None:
        self.plays = 0

    async def play(self) -> None:
        self.plays += 1


def test_bpm_to_parameters_exposes_millisecond_values() -> None:
    parameters = bpm_to_parameters(120.0)

    assert parameters.quarter_ms == pytest.approx(500.0)
    assert parameters.eighth_ms == pytest.approx(250.0)
    assert parameters.half_ms == pytest.approx(1000.0)
    assert parameters.whole_ms == pytest.approx(2000.0)
    assert parameters.ppqn_tick_ms == pytest.approx(500.0 / 24.0)
    assert parameters.bar_4_4_ms == pytest.approx(2000.0)


def test_master_clock_outputs_midi_ticks_and_clicks() -> None:
    async def scenario() -> tuple[list[MidiMessageEvent], list[ClickEvent], FakeClickPlayer]:
        bus = EventBus()
        midi_events: list[MidiMessageEvent] = []
        click_events: list[ClickEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: midi_events.append(event))
        bus.subscribe(ClickEvent, lambda event: click_events.append(event))
        click_player = FakeClickPlayer()
        clock = MasterClock(
            MasterClockConfig(
                enabled=True,
                output_targets=["usb_midi"],
                click_enabled=True,
                click_interval="quarter",
            ),
            bus,
            click_player=click_player,
        )

        await clock.emit_tick()
        await clock.emit_tick()
        return midi_events, click_events, click_player

    midi_events, click_events, click_player = asyncio.run(scenario())

    assert [event.status for event in midi_events] == [MIDI_TIMING_CLOCK, MIDI_TIMING_CLOCK]
    assert all(event.target == "usb_midi" for event in midi_events)
    assert click_player.plays == 1
    assert len(click_events) == 1
    assert click_events[0].position_ticks == 0


def test_master_clock_responds_to_midi_transport_messages() -> None:
    async def scenario() -> tuple[MasterClock, list[MidiMessageEvent]]:
        bus = EventBus()
        midi_events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: midi_events.append(event))
        clock = MasterClock(
            MasterClockConfig(enabled=True, output_targets=["usb_midi"]),
            bus,
        )

        await clock.handle_midi_message(MidiMessageEvent(source="usb", status=MIDI_START))
        await clock.handle_midi_message(MidiMessageEvent(source="usb", status=MIDI_STOP))
        return clock, midi_events

    clock, midi_events = asyncio.run(scenario())

    assert clock.running is False
    assert [event.status for event in midi_events] == [MIDI_START, MIDI_STOP]
    assert all(event.direction == "output" for event in midi_events)


def test_master_clock_bpm_can_be_set_by_osc() -> None:
    async def scenario() -> tuple[MasterClock, list[ControlEvent]]:
        bus = EventBus()
        controls: list[ControlEvent] = []
        bus.subscribe(ControlEvent, lambda event: controls.append(event))
        clock = MasterClock(MasterClockConfig(enabled=True), bus)

        await clock.handle_osc_message(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/clock/bpm",
                arguments=(128.5,),
            )
        )
        return clock, controls

    clock, controls = asyncio.run(scenario())

    assert clock.bpm == pytest.approx(128.5)
    assert any(event.control == "bpm" and event.value == pytest.approx(128.5) for event in controls)
    assert any(event.control == "quarter_ms" for event in controls)


def test_master_clock_bpm_and_click_interval_can_be_set_by_midi_cc() -> None:
    async def scenario() -> MasterClock:
        bus = EventBus()
        clock = MasterClock(
            MasterClockConfig(
                enabled=True,
                bpm_min=60.0,
                bpm_max=180.0,
                bpm_msb_cc=20,
                bpm_lsb_cc=21,
                click_interval_cc=22,
            ),
            bus,
        )

        await clock.handle_midi_message(
            MidiMessageEvent(source="usb", status=0xB0, data=(20, 127))
        )
        await clock.handle_midi_message(
            MidiMessageEvent(source="usb", status=0xB0, data=(21, 127))
        )
        await clock.handle_midi_message(
            MidiMessageEvent(source="usb", status=0xB0, data=(22, 70))
        )
        return clock

    clock = asyncio.run(scenario())

    assert clock.bpm == pytest.approx(180.0)
    assert clock.click_interval == "half"


def test_master_clock_can_be_reconfigured_at_runtime() -> None:
    async def scenario() -> MasterClock:
        bus = EventBus()
        clock = MasterClock(MasterClockConfig(enabled=True, bpm=120.0), bus)

        await clock.configure(
            MasterClockConfig(
                enabled=True,
                bpm=96.0,
                bpm_min=40.0,
                bpm_max=200.0,
                output_targets=["usb_midi"],
                click_enabled=True,
                click_interval="eighth",
                click_wav="/tmp/click.wav",
            )
        )
        return clock

    clock = asyncio.run(scenario())

    assert clock.config.output_targets == ["usb_midi"]
    assert clock.bpm == pytest.approx(96.0)
    assert clock.click_interval == "eighth"
    assert clock.config.click_enabled is True
