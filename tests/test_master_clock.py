import asyncio
import logging

import pytest

from midijuggler.config import MasterClockConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ClickEvent, ControlEvent, MidiMessageEvent, OscMessageEvent
from midijuggler.master_clock import (
    MIDI_START,
    MIDI_STOP,
    MIDI_TIMING_CLOCK,
    MasterClock,
    ClickPlayer,
    bpm_to_parameters,
)


class FakeClickPlayer:
    def __init__(self) -> None:
        self.plays = 0

    async def play(self) -> None:
        self.plays += 1


class SlowClickPlayer:
    def __init__(self) -> None:
        self.plays = 0
        self.release = asyncio.Event()

    async def play(self) -> None:
        self.plays += 1
        await self.release.wait()


class FakeFailedProcess:
    returncode = 1

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b"aplay: audio open error: Permission denied\n"


class FakeBusyProcess:
    returncode = 1

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b"aplay: audio open error: Device or resource busy\n"


class FakeLongProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self._finished = asyncio.Event()

    async def communicate(self) -> tuple[bytes, bytes]:
        await self._finished.wait()
        return b"", b""

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self._finished.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._finished.set()

    async def wait(self) -> int | None:
        await self._finished.wait()
        return self.returncode


def test_bpm_to_parameters_exposes_millisecond_values() -> None:
    parameters = bpm_to_parameters(120.0)

    assert parameters.quarter_ms == pytest.approx(500.0)
    assert parameters.eighth_ms == pytest.approx(250.0)
    assert parameters.half_ms == pytest.approx(1000.0)
    assert parameters.whole_ms == pytest.approx(2000.0)
    assert parameters.ppqn_tick_ms == pytest.approx(500.0 / 24.0)
    assert parameters.bar_4_4_ms == pytest.approx(2000.0)


def test_click_player_logs_nonzero_aplay_exit(caplog) -> None:
    async def scenario() -> None:
        player = ClickPlayer("/tmp/click.wav")
        with caplog.at_level(logging.WARNING, logger="midijuggler.master_clock"):
            await player._wait_for_process(FakeFailedProcess())  # type: ignore[arg-type]

    asyncio.run(scenario())

    assert "click playback command exited with status 1" in caplog.text
    assert "Permission denied" in caplog.text


def test_click_player_does_not_warn_for_busy_audio_device(caplog) -> None:
    async def scenario() -> None:
        player = ClickPlayer("/tmp/click.wav")
        with caplog.at_level(logging.WARNING, logger="midijuggler.master_clock"):
            await player._wait_for_process(FakeBusyProcess())  # type: ignore[arg-type]

    asyncio.run(scenario())

    assert "Device or resource busy" not in caplog.text


def test_click_player_restarts_previous_process_when_overlap_is_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    async def scenario() -> list[FakeLongProcess]:
        wav = tmp_path / "click.wav"
        wav.write_bytes(b"fake")
        processes: list[FakeLongProcess] = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            process = FakeLongProcess()
            processes.append(process)
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        player = ClickPlayer(str(wav), allow_overlap=False)
        await player.play()
        await asyncio.sleep(0)
        await player.play()
        await asyncio.sleep(0)

        for process in processes:
            if process.returncode is None:
                process.terminate()
        await asyncio.sleep(0)
        return processes

    processes = asyncio.run(scenario())

    assert len(processes) == 2
    assert processes[0].terminated is True
    assert processes[1].terminated is True


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
        await asyncio.sleep(0)
        return midi_events, click_events, click_player

    midi_events, click_events, click_player = asyncio.run(scenario())

    assert [event.status for event in midi_events] == [MIDI_TIMING_CLOCK, MIDI_TIMING_CLOCK]
    assert all(event.target == "usb_midi" for event in midi_events)
    assert click_player.plays == 1
    assert len(click_events) == 1
    assert click_events[0].position_ticks == 0


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
