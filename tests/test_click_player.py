import asyncio
import logging
import struct
import wave

import pytest

from midijuggler.click_player import (
    AplayClickPlayer,
    AlsaClickPlayer,
    create_click_player,
    load_wav,
)


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


class FakePcm:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.drops = 0
        self.closed = False

    def drop(self) -> None:
        self.drops += 1

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        self.closed = True


def _write_wav(path, *, channels: int = 1, rate: int = 44100, sample_width: int = 2) -> None:
    frames = struct.pack("<h", 0) * channels
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(rate)
        wav_file.writeframes(frames)


def test_load_wav_reads_sample_data(tmp_path) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path, channels=2, rate=48000)

    wav = load_wav(wav_path)

    assert wav.channels == 2
    assert wav.rate == 48000
    assert wav.sample_width == 2
    assert len(wav.frames) == 4


def test_create_click_player_uses_aplay_when_alsaaudio_missing(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.click_player._alsaaudio_available", lambda: False)

    player = create_click_player("/tmp/click.wav")

    assert isinstance(player, AplayClickPlayer)


def test_create_click_player_uses_alsa_when_available(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.click_player._alsaaudio_available", lambda: True)
    monkeypatch.setattr(AlsaClickPlayer, "__init__", lambda self, *args, **kwargs: None)

    player = create_click_player("/tmp/click.wav")

    assert isinstance(player, AlsaClickPlayer)


def test_aplay_click_player_logs_nonzero_exit(caplog) -> None:
    async def scenario() -> None:
        player = AplayClickPlayer("/tmp/click.wav")
        with caplog.at_level(logging.WARNING, logger="midijuggler.click_player"):
            await player._wait_for_process(FakeFailedProcess())  # type: ignore[arg-type]

    asyncio.run(scenario())

    assert "click playback command exited with status 1" in caplog.text
    assert "Permission denied" in caplog.text


def test_aplay_click_player_does_not_warn_for_busy_audio_device(caplog) -> None:
    async def scenario() -> None:
        player = AplayClickPlayer("/tmp/click.wav")
        with caplog.at_level(logging.WARNING, logger="midijuggler.click_player"):
            await player._wait_for_process(FakeBusyProcess())  # type: ignore[arg-type]

    asyncio.run(scenario())

    assert "Device or resource busy" not in caplog.text


def test_aplay_click_player_restarts_previous_process_when_overlap_is_disabled(
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

        player = AplayClickPlayer(str(wav), allow_overlap=False)
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


def test_alsa_click_player_reuses_pcm_and_writes_loaded_wav(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    pcm = FakePcm()

    class FakeAlsaModule:
        PCM_PLAYBACK = "playback"
        PCM_NORMAL = "normal"
        PCM_FORMAT_U8 = "u8"
        PCM_FORMAT_S16_LE = "s16le"
        PCM_FORMAT_S24_3LE = "s24_3le"
        PCM_FORMAT_S32_LE = "s32le"

        class ALSAAudioError(OSError):
            pass

        def PCM(self, **kwargs):
            assert kwargs["device"] == "master_clock"
            assert kwargs["channels"] == 1
            assert kwargs["rate"] == 44100
            return pcm

    monkeypatch.setitem(__import__("sys").modules, "alsaaudio", FakeAlsaModule())

    player = AlsaClickPlayer(str(wav_path), audio_device="master_clock")
    player._play_unlocked()
    player._play_unlocked()

    assert len(pcm.writes) == 2
    assert pcm.drops == 2
    assert pcm.closed is False

    player._close_pcm()
    assert pcm.closed is True


def test_alsa_click_player_serializes_writes_when_overlap_is_disabled(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    pcm = FakePcm()
    active_writes = 0
    max_active_writes = 0

    class FakeAlsaModule:
        PCM_PLAYBACK = "playback"
        PCM_NORMAL = "normal"
        PCM_FORMAT_U8 = "u8"
        PCM_FORMAT_S16_LE = "s16le"
        PCM_FORMAT_S24_3LE = "s24_3le"
        PCM_FORMAT_S32_LE = "s32le"

        class ALSAAudioError(OSError):
            pass

        def PCM(self, **kwargs):
            return pcm

    def slow_write(data: bytes) -> None:
        nonlocal active_writes, max_active_writes
        active_writes += 1
        max_active_writes = max(max_active_writes, active_writes)
        try:
            import time

            time.sleep(0.05)
        finally:
            pcm.writes.append(data)
            active_writes -= 1

    pcm.write = slow_write  # type: ignore[method-assign]
    monkeypatch.setitem(__import__("sys").modules, "alsaaudio", FakeAlsaModule())

    async def scenario() -> int:
        player = AlsaClickPlayer(str(wav_path), allow_overlap=False)
        await asyncio.gather(player.play(), player.play())
        return max_active_writes

    assert asyncio.run(scenario()) == 1


def test_alsa_click_player_overlapping_play_returns_before_write_finishes(
    tmp_path,
    monkeypatch,
) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    pcm = FakePcm()
    active_writes = 0
    max_active_writes = 0

    class FakeAlsaModule:
        PCM_PLAYBACK = "playback"
        PCM_NORMAL = "normal"
        PCM_FORMAT_U8 = "u8"
        PCM_FORMAT_S16_LE = "s16le"
        PCM_FORMAT_S24_3LE = "s24_3le"
        PCM_FORMAT_S32_LE = "s32le"

        class ALSAAudioError(OSError):
            pass

        def PCM(self, **kwargs):
            return pcm

    def slow_write(data: bytes) -> None:
        nonlocal active_writes, max_active_writes
        active_writes += 1
        max_active_writes = max(max_active_writes, active_writes)
        try:
            import time

            time.sleep(0.05)
        finally:
            pcm.writes.append(data)
            active_writes -= 1

    pcm.write = slow_write  # type: ignore[method-assign]
    monkeypatch.setitem(__import__("sys").modules, "alsaaudio", FakeAlsaModule())

    async def scenario() -> tuple[int, int]:
        player = AlsaClickPlayer(str(wav_path), allow_overlap=True)
        await player.play()
        await player.play()
        await asyncio.sleep(0)
        queued = len(pcm.writes)
        await asyncio.sleep(0.12)
        return queued, len(pcm.writes)

    queued, completed = asyncio.run(scenario())

    assert queued == 0
    assert completed == 2
