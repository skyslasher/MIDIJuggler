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
        self.drains = 0
        self.closed = False

    def drop(self) -> None:
        self.drops += 1

    def drain(self) -> None:
        self.drains += 1

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        self.closed = True


def _wait_for_click_writes(pcm: FakePcm, count: int, *, timeout: float = 1.0) -> None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(pcm.writes) >= count:
            return
        time.sleep(0.01)
    assert len(pcm.writes) >= count


def _wait_for_pcm_instances(instances: list[FakePcm], count: int, *, timeout: float = 2.0) -> None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(instances) >= count:
            return
        time.sleep(0.01)
    assert len(instances) >= count


def _fake_alsa_module(**overrides):
    class FakeAlsaModule:
        PCM_PLAYBACK = "playback"
        PCM_NONBLOCK = "nonblock"
        PCM_NORMAL = "normal"
        PCM_FORMAT_U8 = "u8"
        PCM_FORMAT_S16_LE = "s16le"
        PCM_FORMAT_S24_3LE = "s24_3le"
        PCM_FORMAT_S32_LE = "s32le"

        class ALSAAudioError(OSError):
            pass

        def PCM(self, **kwargs):
            assert kwargs.get("mode") == self.PCM_NORMAL
            handler = overrides.get("pcm_factory")
            if handler is not None:
                return handler(kwargs)
            return FakePcm()

    return FakeAlsaModule()


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


def test_create_click_player_uses_alsa_for_wing_dshare_pcm(monkeypatch) -> None:
    monkeypatch.setattr("midijuggler.click_player._alsaaudio_available", lambda: True)
    monkeypatch.setattr(AlsaClickPlayer, "__init__", lambda self, *args, **kwargs: None)

    player = create_click_player("/tmp/click.wav", audio_device="wing_stereo1")

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


def test_alsa_click_player_opens_fresh_pcm_for_each_click(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    created: list[FakePcm] = []

    def pcm_factory(kwargs):
        assert kwargs["device"] == "master_clock"
        assert kwargs["channels"] == 1
        assert kwargs["rate"] == 44100
        pcm = FakePcm()
        created.append(pcm)
        return pcm

    monkeypatch.setitem(
        __import__("sys").modules,
        "alsaaudio",
        _fake_alsa_module(pcm_factory=pcm_factory),
    )

    player = AlsaClickPlayer(str(wav_path), audio_device="master_clock", allow_overlap=True)
    player.trigger()
    player.trigger()
    _wait_for_pcm_instances(created, 2)
    _wait_for_click_writes(created[0], 1)
    _wait_for_click_writes(created[1], 1)

    assert len(created) == 2
    assert len(created[0].writes) == 1
    assert len(created[1].writes) == 1
    assert created[0].drains == 0
    assert all(pcm.closed is True for pcm in created)

    asyncio.run(player.close())


def test_alsa_click_player_prepare_opens_pcm_before_play(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    created: list[FakePcm] = []

    def pcm_factory(kwargs):
        assert kwargs["device"] == "wing_stereo1"
        pcm = FakePcm()
        created.append(pcm)
        return pcm

    monkeypatch.setitem(
        __import__("sys").modules,
        "alsaaudio",
        _fake_alsa_module(pcm_factory=pcm_factory),
    )

    async def scenario() -> None:
        player = AlsaClickPlayer(str(wav_path), audio_device="wing_stereo1", allow_overlap=False)
        assert await player.prepare() is True
        assert len(created) == 1
        assert created[0].closed is True
        player.trigger()
        _wait_for_pcm_instances(created, 2)
        _wait_for_click_writes(created[1], 1)
        assert len(created[1].writes) == 1
        await player.release()
        await player.close()

    asyncio.run(scenario())


def test_alsa_click_player_rapid_triggers_queue_all_writes(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    pcm = FakePcm()
    active_writes = 0
    max_active_writes = 0

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
    monkeypatch.setitem(
        __import__("sys").modules,
        "alsaaudio",
        _fake_alsa_module(pcm_factory=lambda kwargs: pcm),
    )

    player = AlsaClickPlayer(str(wav_path), allow_overlap=False)
    player.trigger()
    player.trigger()
    _wait_for_click_writes(pcm, 2, timeout=2.0)

    assert max_active_writes >= 1
    assert len(pcm.writes) == 2
    assert pcm.drains == 0
    asyncio.run(player.close())


def test_alsa_click_player_recovers_from_bad_pcm_state(tmp_path, monkeypatch, caplog) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    wav = load_wav(wav_path)
    created: list[FakePcm] = []

    class FakeAlsaModule:
        PCM_PLAYBACK = "playback"
        PCM_NONBLOCK = "nonblock"
        PCM_NORMAL = "normal"
        PCM_FORMAT_U8 = "u8"
        PCM_FORMAT_S16_LE = "s16le"
        PCM_FORMAT_S24_3LE = "s24_3le"
        PCM_FORMAT_S32_LE = "s32le"

        class ALSAAudioError(OSError):
            pass

        def PCM(self, **kwargs):
            pcm = FakePcm()
            created.append(pcm)
            if len(created) == 1:

                def flaky_write(data: bytes) -> None:
                    raise FakeAlsaModule.ALSAAudioError(
                        "File descriptor in bad state [master_clock]"
                    )

                pcm.write = flaky_write  # type: ignore[method-assign]
            return pcm

    monkeypatch.setitem(__import__("sys").modules, "alsaaudio", FakeAlsaModule())

    player = AlsaClickPlayer(str(wav_path), audio_device="master_clock", allow_overlap=True)
    with caplog.at_level(logging.DEBUG, logger="midijuggler.click_player"):
        player.trigger()
        import time

        deadline = time.time() + 1.0
        while time.time() < deadline:
            if len(created) >= 2 and len(created[1].writes) >= 1:
                break
            time.sleep(0.01)

    assert len(created) == 2
    assert created[1].writes == [wav.frames]
    assert "recreating ALSA PCM after" in caplog.text
    asyncio.run(player.close())


def test_alsa_click_player_recovers_from_invalid_argument_on_open(
    tmp_path, monkeypatch, caplog
) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    wav = load_wav(wav_path)
    created: list[FakePcm] = []

    class FakeAlsaModule:
        PCM_PLAYBACK = "playback"
        PCM_NONBLOCK = "nonblock"
        PCM_NORMAL = "normal"
        PCM_FORMAT_U8 = "u8"
        PCM_FORMAT_S16_LE = "s16le"
        PCM_FORMAT_S24_3LE = "s24_3le"
        PCM_FORMAT_S32_LE = "s32le"

        class ALSAAudioError(OSError):
            pass

        def PCM(self, **kwargs):
            pcm = FakePcm()
            created.append(pcm)
            if len(created) == 1:

                def flaky_write(data: bytes) -> None:
                    raise FakeAlsaModule.ALSAAudioError(
                        "Invalid argument [wing_stereo1]"
                    )

                pcm.write = flaky_write  # type: ignore[method-assign]
            return pcm

    monkeypatch.setitem(__import__("sys").modules, "alsaaudio", FakeAlsaModule())

    player = AlsaClickPlayer(str(wav_path), audio_device="wing_stereo1", allow_overlap=True)
    with caplog.at_level(logging.DEBUG, logger="midijuggler.click_player"):
        player.trigger()
        import time

        deadline = time.time() + 1.0
        while time.time() < deadline:
            if len(created) >= 2 and len(created[1].writes) >= 1:
                break
            time.sleep(0.01)

    assert len(created) == 2
    assert created[1].writes == [wav.frames]
    asyncio.run(player.close())


def test_alsa_click_player_write_loop_retries_zero_length_writes(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    pcm = FakePcm()
    attempts = {"count": 0}

    def flaky_write(data: bytes) -> int:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return 0
        pcm.writes.append(data)
        return len(data) // 2

    pcm.write = flaky_write  # type: ignore[method-assign]
    monkeypatch.setitem(
        __import__("sys").modules,
        "alsaaudio",
        _fake_alsa_module(pcm_factory=lambda kwargs: pcm),
    )

    player = AlsaClickPlayer(str(wav_path), audio_device="master_clock")
    player.trigger()
    _wait_for_click_writes(pcm, 1)

    assert attempts["count"] >= 2
    asyncio.run(player.close())


def test_alsa_click_player_trigger_returns_before_write_finishes(
    tmp_path,
    monkeypatch,
) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    pcm = FakePcm()

    def slow_write(data: bytes) -> None:
        import time

        time.sleep(0.05)
        pcm.writes.append(data)

    pcm.write = slow_write  # type: ignore[method-assign]
    monkeypatch.setitem(
        __import__("sys").modules,
        "alsaaudio",
        _fake_alsa_module(pcm_factory=lambda kwargs: pcm),
    )

    player = AlsaClickPlayer(str(wav_path), allow_overlap=True)
    player.trigger()
    player.trigger()
    assert len(pcm.writes) == 0
    _wait_for_click_writes(pcm, 2, timeout=2.0)
    assert len(pcm.writes) == 2
    asyncio.run(player.close())


def test_alsa_click_player_retries_when_device_is_busy(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "click.wav"
    _write_wav(wav_path)
    pcm = FakePcm()
    attempts = {"count": 0}

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

    def busy_once(data: bytes) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise FakeAlsaModule.ALSAAudioError("Device or resource busy")
        pcm.writes.append(data)

    pcm.write = busy_once  # type: ignore[method-assign]
    monkeypatch.setitem(__import__("sys").modules, "alsaaudio", FakeAlsaModule())

    player = AlsaClickPlayer(str(wav_path), audio_device="wing_stereo1")
    player.trigger()
    _wait_for_click_writes(pcm, 1)

    assert attempts["count"] >= 2
    asyncio.run(player.close())
