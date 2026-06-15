import asyncio
import contextlib
import logging

import pytest

from midijuggler.alsa import MASTER_CLOCK_PCM_NAME
from midijuggler.click_player import AplayClickPlayer
from midijuggler.config import MasterClockConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ClickEvent, ControlEvent, MasterClockCommandEvent, MidiMessageEvent, OscMessageEvent
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

    async def close(self) -> None:
        return


class SlowClickPlayer:
    def __init__(self) -> None:
        self.plays = 0
        self.release = asyncio.Event()

    async def play(self) -> None:
        self.plays += 1
        await self.release.wait()

    async def close(self) -> None:
        return


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
                output_targets=["midi"],
                click_enabled=True,
                click_interval="quarter",
            ),
            bus,
            click_player=click_player,
        )

        await clock.emit_tick()
        await clock.emit_tick()
        await asyncio.sleep(0)
        return midi_events, click_events, click_player

    midi_events, click_events, click_player = asyncio.run(scenario())

    assert [event.status for event in midi_events] == [MIDI_TIMING_CLOCK, MIDI_TIMING_CLOCK]
    assert all(event.target == "midi" for event in midi_events)
    assert click_player.plays == 1
    assert len(click_events) == 1
    assert click_events[0].position_ticks == 0


def test_master_clock_publishes_click_events_without_audio_click() -> None:
    async def scenario() -> tuple[FakeClickPlayer, list[ClickEvent]]:
        bus = EventBus()
        click_events: list[ClickEvent] = []
        bus.subscribe(ClickEvent, lambda event: click_events.append(event))
        click_player = FakeClickPlayer()
        clock = MasterClock(
            MasterClockConfig(
                enabled=True,
                click_enabled=False,
                click_interval="quarter",
            ),
            bus,
            click_player=click_player,
        )

        await clock.emit_tick()
        await asyncio.sleep(0)
        return click_player, click_events

    click_player, click_events = asyncio.run(scenario())

    assert click_player.plays == 0
    assert len(click_events) == 1


def test_master_clock_uses_overlapping_click_playback_for_generated_pcm() -> None:
    clock = MasterClock(
        MasterClockConfig(),
        EventBus(),
        click_audio_device=MASTER_CLOCK_PCM_NAME,
    )

    assert isinstance(clock.click_player, AplayClickPlayer)
    assert clock.click_player.allow_overlap is True


def test_master_clock_triggers_clicks_without_waiting_for_previous_playback() -> None:
    async def scenario() -> SlowClickPlayer:
        bus = EventBus()
        click_player = SlowClickPlayer()
        clock = MasterClock(
            MasterClockConfig(
                enabled=True,
                click_enabled=True,
                click_interval="eighth",
            ),
            bus,
            click_player=click_player,
        )

        await clock.emit_tick()
        for _ in range(11):
            await clock.emit_tick()
        await clock.emit_tick()
        await asyncio.sleep(0)
        click_player.release.set()
        await asyncio.sleep(0)
        return click_player

    click_player = asyncio.run(scenario())

    assert click_player.plays == 2


def test_set_bpm_while_running_does_not_reset_transport_position_ticks() -> None:
    async def scenario() -> MasterClock:
        bus = EventBus()
        clock = MasterClock(
            MasterClockConfig(enabled=True, click_enabled=True, click_interval="quarter"),
            bus,
            click_player=FakeClickPlayer(),
        )
        clock.running = True
        clock.position_ticks = 18
        await clock.set_bpm(130.0)
        return clock

    clock = asyncio.run(scenario())

    assert clock.position_ticks == 18
    assert clock.bpm == pytest.approx(130.0)


def test_set_bpm_while_running_preserves_next_click_on_emit_tick() -> None:
    async def scenario() -> tuple[MasterClock, list[ClickEvent]]:
        bus = EventBus()
        click_events: list[ClickEvent] = []
        bus.subscribe(ClickEvent, lambda event: click_events.append(event))
        clock = MasterClock(
            MasterClockConfig(enabled=True, click_enabled=True, click_interval="quarter"),
            bus,
            click_player=FakeClickPlayer(),
        )
        clock.running = True
        clock.position_ticks = 23
        await clock.set_bpm(121.0)
        await clock.emit_tick()
        await clock.emit_tick()
        return clock, click_events

    clock, click_events = asyncio.run(scenario())

    assert clock.bpm == pytest.approx(121.0)
    assert clock.position_ticks == 25
    assert len(click_events) == 1


def test_click_and_midi_tick_share_the_same_transport_frame() -> None:
    async def scenario() -> tuple[list[MidiMessageEvent], list[ClickEvent]]:
        bus = EventBus()
        midi_events: list[MidiMessageEvent] = []
        click_events: list[ClickEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: midi_events.append(event))
        bus.subscribe(ClickEvent, lambda event: click_events.append(event))
        clock = MasterClock(
            MasterClockConfig(
                enabled=True,
                output_targets=["midi"],
                click_enabled=True,
                click_interval="quarter",
            ),
            bus,
            click_player=FakeClickPlayer(),
        )
        await clock.emit_tick()
        return midi_events, click_events

    midi_events, click_events = asyncio.run(scenario())

    assert len(midi_events) == 1
    assert len(click_events) == 1
    assert click_events[0].position_ticks == 0


def test_set_bpm_schedules_notifications_without_blocking_transport() -> None:
    async def scenario() -> tuple[MasterClock, int, float]:
        bus = EventBus()
        broadcasts = 0

        async def slow_broadcast(_event) -> None:
            nonlocal broadcasts
            broadcasts += 1
            await asyncio.sleep(0.05)

        bus.subscribe("*", slow_broadcast)
        clock = MasterClock(
            MasterClockConfig(enabled=True, click_enabled=True, click_interval="eighth", bpm=120.0),
            bus,
            click_player=FakeClickPlayer(),
        )
        await clock.start_transport(reset_position=True)
        ticks_before = clock.position_ticks
        started = asyncio.get_running_loop().time()
        for step in range(12):
            await clock.set_bpm(120.0 + step * 0.5)
        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(0.12)
        return clock, ticks_before, elapsed

    clock, ticks_before, elapsed = asyncio.run(scenario())

    assert elapsed < 0.08
    assert clock.position_ticks > ticks_before


def test_rapid_bpm_changes_keep_transport_frames_and_clicks_advancing() -> None:
    async def scenario() -> tuple[int, int, list[ClickEvent]]:
        bus = EventBus()
        click_events: list[ClickEvent] = []
        bus.subscribe(ClickEvent, lambda event: click_events.append(event))
        clock = MasterClock(
            MasterClockConfig(
                enabled=True,
                click_enabled=True,
                click_interval="eighth",
                bpm=240.0,
            ),
            bus,
            click_player=FakeClickPlayer(),
        )
        await clock.start_transport(reset_position=True)
        ticks_before = clock.position_ticks
        for step in range(24):
            await clock.set_bpm(240.0 + step * 0.5)
            await asyncio.sleep(0)
        await asyncio.sleep(0.15)
        return ticks_before, clock.position_ticks, click_events

    ticks_before, ticks_after, click_events = asyncio.run(scenario())

    assert ticks_after > ticks_before
    assert click_events


def test_master_clock_start_command_while_running_does_not_reset_position() -> None:
    async def scenario() -> MasterClock:
        bus = EventBus()
        clock = MasterClock(MasterClockConfig(enabled=True, output_targets=["midi"]), bus)
        clock.running = True
        for _ in range(8):
            await clock.emit_tick()
        await clock.handle_command(
            MasterClockCommandEvent(source="test", command="start")
        )
        return clock

    clock = asyncio.run(scenario())

    assert clock.running is True
    assert clock.position_ticks == 8


def test_set_bpm_while_running_preserves_position() -> None:
    async def scenario() -> tuple[MasterClock, list[MidiMessageEvent]]:
        bus = EventBus()
        midi_events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: midi_events.append(event))
        clock = MasterClock(MasterClockConfig(enabled=True, output_targets=["midi"]), bus)
        clock.running = True
        for _ in range(6):
            await clock.emit_tick()
        midi_events.clear()
        await clock.set_bpm(128.5)
        return clock, midi_events

    clock, midi_events = asyncio.run(scenario())

    assert clock.running is True
    assert clock.position_ticks == 6
    assert clock.bpm == pytest.approx(128.5)
    assert [event.status for event in midi_events] == []


def test_start_transport_while_running_preserves_position() -> None:
    async def scenario() -> tuple[MasterClock, list[MidiMessageEvent]]:
        bus = EventBus()
        midi_events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: midi_events.append(event))
        clock = MasterClock(MasterClockConfig(enabled=True, output_targets=["midi"]), bus)
        await clock.start_transport(reset_position=True)
        if clock._transport_task is not None:
            clock._transport_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await clock._transport_task
            clock._transport_task = None
        for _ in range(9):
            await clock.emit_tick()
        midi_events.clear()
        await clock.start_transport(reset_position=True)
        if clock._transport_task is not None:
            clock._transport_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await clock._transport_task
            clock._transport_task = None
        return clock, midi_events

    clock, midi_events = asyncio.run(scenario())

    assert clock.running is True
    assert clock.position_ticks == 9
    assert [event.status for event in midi_events] == []


def test_master_clock_responds_to_midi_transport_messages() -> None:
    async def scenario() -> tuple[MasterClock, list[MidiMessageEvent]]:
        bus = EventBus()
        midi_events: list[MidiMessageEvent] = []
        bus.subscribe(MidiMessageEvent, lambda event: midi_events.append(event))
        clock = MasterClock(
            MasterClockConfig(enabled=True, output_targets=["midi"]),
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
        await clock.flush_bpm_notifications()
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
                output_targets=["midi"],
                click_enabled=True,
                click_interval="eighth",
                click_wav="/tmp/click.wav",
            )
        )
        return clock

    clock = asyncio.run(scenario())

    assert clock.config.output_targets == ["midi"]
    assert clock.bpm == pytest.approx(96.0)
    assert clock.click_interval == "eighth"
    assert clock.config.click_enabled is True
