"""Audio click playback through persistent ALSA or aplay fallback."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WavPlaybackData:
    """Decoded WAV samples ready for ALSA playback."""

    frames: bytes
    channels: int
    rate: int
    sample_width: int


class ClickPlayer(Protocol):
    """Common interface for master-clock click playback."""

    async def play(self) -> None: ...

    async def close(self) -> None: ...


def create_click_player(
    wav_path: str,
    *,
    command: str = "aplay",
    audio_device: str = "",
    environment: dict[str, str] | None = None,
    allow_overlap: bool = True,
) -> ClickPlayer:
    """Create the best available click player for the current host."""

    if _alsaaudio_available():
        try:
            return AlsaClickPlayer(
                wav_path,
                audio_device=audio_device,
                environment=environment,
                allow_overlap=allow_overlap,
            )
        except Exception:
            LOGGER.exception("failed to initialize ALSA click player; falling back to aplay")

    LOGGER.debug("using aplay fallback for click playback")
    return AplayClickPlayer(
        wav_path,
        command=command,
        audio_device=audio_device,
        environment=environment,
        allow_overlap=allow_overlap,
    )


def load_wav(path: str | Path) -> WavPlaybackData:
    """Load a WAV file into memory for repeated playback."""

    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        rate = wav_file.getframerate()
        if channels < 1:
            raise ValueError("WAV must contain at least one channel")
        if sample_width not in {1, 2, 3, 4}:
            raise ValueError(f"unsupported WAV sample width: {sample_width}")
        frames = wav_file.readframes(wav_file.getnframes())

    return WavPlaybackData(
        frames=frames,
        channels=channels,
        rate=rate,
        sample_width=sample_width,
    )


class AlsaClickPlayer:
    """Play clicks through a persistent ALSA PCM handle."""

    def __init__(
        self,
        wav_path: str,
        audio_device: str = "",
        environment: dict[str, str] | None = None,
        allow_overlap: bool = True,
    ) -> None:
        import alsaaudio

        self._alsaaudio = alsaaudio
        self.wav_path = wav_path
        self.audio_device = audio_device
        self.environment = environment or {}
        self.allow_overlap = allow_overlap
        self._wav: WavPlaybackData | None = None
        self._pcm: Any | None = None
        self._configured_wav_path = ""
        self._configured_device = ""
        self._play_lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    async def play(self) -> None:
        if not self.wav_path:
            return
        if not Path(self.wav_path).is_file():
            LOGGER.warning("click WAV does not exist: %s", self.wav_path)
            return

        if not self.allow_overlap:
            async with self._async_lock:
                await asyncio.to_thread(self._play_locked)
            return

        asyncio.create_task(self._play_overlapping(), name="click-playback")

    async def _play_overlapping(self) -> None:
        await asyncio.to_thread(self._play_unlocked)

    async def close(self) -> None:
        async with self._async_lock:
            await asyncio.to_thread(self._close_pcm)

    def _play_locked(self) -> None:
        with self._play_lock:
            self._play_unlocked()

    def _play_unlocked(self) -> None:
        try:
            self._ensure_pcm()
            assert self._pcm is not None
            assert self._wav is not None
            self._pcm.prepare()
            self._pcm.write(self._wav.frames)
        except self._alsaaudio.ALSAAudioError as exc:
            message = str(exc)
            if "Device or resource busy" in message or "Resource busy" in message:
                LOGGER.debug("click playback skipped because audio device is busy: %s", message)
                return
            LOGGER.warning("ALSA click playback failed: %s", message)
            self._close_pcm()
        except OSError:
            LOGGER.exception("failed to play click through ALSA")
            self._close_pcm()

    def _ensure_pcm(self) -> None:
        device = self.audio_device or "default"
        if (
            self._pcm is not None
            and self._configured_wav_path == self.wav_path
            and self._configured_device == device
        ):
            return

        wav = load_wav(self.wav_path)
        self._close_pcm()
        with _alsa_environment(self.environment):
            pcm = self._alsaaudio.PCM(
                type=self._alsaaudio.PCM_PLAYBACK,
                mode=self._alsaaudio.PCM_NORMAL,
                device=device,
                channels=wav.channels,
                rate=wav.rate,
                format=_sample_width_to_format(self._alsaaudio, wav.sample_width),
                periodsize=1024,
            )
        self._pcm = pcm
        self._wav = wav
        self._configured_wav_path = self.wav_path
        self._configured_device = device

    def _close_pcm(self) -> None:
        if self._pcm is None:
            return
        with contextlib.suppress(Exception):
            self._pcm.close()
        self._pcm = None
        self._wav = None
        self._configured_wav_path = ""
        self._configured_device = ""


class AplayClickPlayer:
    """Play an audio click WAV through ALSA's aplay command."""

    def __init__(
        self,
        wav_path: str,
        command: str = "aplay",
        audio_device: str = "",
        environment: dict[str, str] | None = None,
        allow_overlap: bool = True,
    ) -> None:
        self.wav_path = wav_path
        self.command = command
        self.audio_device = audio_device
        self.environment = environment or {}
        self.allow_overlap = allow_overlap
        self._lock = asyncio.Lock()
        self._process_tasks: dict[asyncio.subprocess.Process, asyncio.Task[None]] = {}

    async def play(self) -> None:
        if not self.wav_path:
            return
        if not Path(self.wav_path).is_file():
            LOGGER.warning("click WAV does not exist: %s", self.wav_path)
            return

        command = [self.command, "-q"]
        if self.audio_device:
            command.extend(["-D", self.audio_device])
        command.append(self.wav_path)

        async with self._lock:
            if not self.allow_overlap:
                await self._stop_active_processes()

            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ, **self.environment} if self.environment else None,
                )
            except OSError:
                LOGGER.exception("failed to start click playback command")
                return

            task = asyncio.create_task(self._wait_for_process(process), name="click-playback")
            self._process_tasks[process] = task

    async def close(self) -> None:
        async with self._lock:
            await self._stop_active_processes()

    async def _wait_for_process(self, process: asyncio.subprocess.Process) -> None:
        try:
            _, stderr = await process.communicate()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("click playback command failed while waiting")
            return
        finally:
            self._process_tasks.pop(process, None)

        if process.returncode:
            message = stderr.decode(errors="replace").strip() if stderr else ""
            if "Device or resource busy" in message:
                LOGGER.debug(
                    "click playback skipped because audio device is busy: %s",
                    message,
                )
                return
            LOGGER.warning(
                "click playback command exited with status %s%s",
                process.returncode,
                f": {message}" if message else "",
            )

    async def _stop_active_processes(self) -> None:
        for process, task in list(self._process_tasks.items()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.2)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    with contextlib.suppress(Exception):
                        await process.wait()
            self._process_tasks.pop(process, None)


def _alsaaudio_available() -> bool:
    try:
        import alsaaudio  # noqa: F401
    except ImportError:
        return False
    return True


def _sample_width_to_format(alsaaudio: Any, sample_width: int) -> int:
    formats = {
        1: alsaaudio.PCM_FORMAT_U8,
        2: alsaaudio.PCM_FORMAT_S16_LE,
        3: alsaaudio.PCM_FORMAT_S24_3LE,
        4: alsaaudio.PCM_FORMAT_S32_LE,
    }
    try:
        return formats[sample_width]
    except KeyError as exc:
        raise ValueError(f"unsupported WAV sample width: {sample_width}") from exc


@contextlib.contextmanager
def _alsa_environment(environment: dict[str, str]):
    if not environment:
        yield
        return

    previous = {key: os.environ.get(key) for key in environment}
    os.environ.update(environment)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
