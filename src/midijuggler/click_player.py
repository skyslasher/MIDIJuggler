"""Audio click playback through a dedicated realtime thread or aplay fallback."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import queue
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from midijuggler.alsa import is_wing_routing_pcm

LOGGER = logging.getLogger(__name__)

_CLICK_THREAD_POLL_S = 0.05
_CLICK_REALTIME_PRIORITY = 50
_PLAYBACK_PERIOD_FRAMES = 1024
_MAX_WRITE_RECOVERY_ATTEMPTS = 2


@dataclass(frozen=True)
class WavPlaybackData:
    """Decoded WAV samples ready for ALSA playback."""

    frames: bytes
    channels: int
    rate: int
    sample_width: int


@dataclass
class _PrepareCommand:
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[bool]


@dataclass
class _ReleaseCommand:
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[None]


@dataclass
class _CloseCommand:
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[None]


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

    del allow_overlap  # overlap is always handled by the threaded ALSA player

    if _alsaaudio_available():
        try:
            return AlsaClickPlayer(
                wav_path,
                audio_device=audio_device,
                environment=environment,
                command=command,
            )
        except Exception:
            LOGGER.exception("failed to initialize ALSA click player; falling back to aplay")

    LOGGER.debug("using aplay fallback for click playback")
    return AplayClickPlayer(
        wav_path,
        command=command,
        audio_device=audio_device,
        environment=environment,
        allow_overlap=True,
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
    """Play clicks on a dedicated thread with overlapping ALSA writes."""

    def __init__(
        self,
        wav_path: str,
        audio_device: str = "",
        environment: dict[str, str] | None = None,
        allow_overlap: bool = True,
        command: str = "aplay",
    ) -> None:
        import alsaaudio

        del allow_overlap
        self._alsaaudio = alsaaudio
        self.command = command
        self.wav_path = wav_path
        self.audio_device = audio_device
        self.environment = environment or {}
        self._wav: WavPlaybackData | None = None
        self._configured_wav_path = ""
        self._playback_pcm: Any | None = None
        self._playback_device = ""
        self._playback_period_frames = _PLAYBACK_PERIOD_FRAMES
        self._click_queue: queue.SimpleQueue[None] = queue.SimpleQueue()
        self._command_queue: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._missing_device_warning_logged = False
        self._audio_device_unavailable = False
        self._worker = threading.Thread(
            target=self._worker_main,
            name="midijuggler-click-audio",
            daemon=True,
        )
        self._worker.start()

    @property
    def allow_overlap(self) -> bool:
        return True

    def trigger(self) -> None:
        """Queue one click from the master clock without touching asyncio."""

        if not self.wav_path or not Path(self.wav_path).is_file():
            return
        self._click_queue.put_nowait(None)
        self._wake_event.set()

    async def play(self) -> None:
        self.trigger()

    async def prepare(self) -> bool:
        if not self.wav_path or not Path(self.wav_path).is_file():
            return False
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._command_queue.put(_PrepareCommand(loop=loop, future=future))
        return await future

    async def release(self) -> None:
        await self._run_release_command()

    async def close(self) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        self._command_queue.put(_CloseCommand(loop=loop, future=future))
        await future
        self._worker.join(timeout=2.0)

    async def _run_release_command(self) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        self._command_queue.put(_ReleaseCommand(loop=loop, future=future))
        await future

    def _worker_main(self) -> None:
        _try_set_realtime_priority()
        while not self._stop_event.is_set():
            self._process_commands()
            had_clicks = self._process_click_queue()
            if self._stop_event.is_set() and self._click_queue.empty():
                break
            if had_clicks or self._wake_event.is_set():
                self._wake_event.clear()
                continue
            self._wake_event.wait(timeout=_CLICK_THREAD_POLL_S)
            self._wake_event.clear()

    def _process_commands(self) -> None:
        while True:
            try:
                command = self._command_queue.get_nowait()
            except queue.Empty:
                return
            if isinstance(command, _PrepareCommand):
                self._handle_prepare(command)
            elif isinstance(command, _ReleaseCommand):
                self._handle_release(command)
            elif isinstance(command, _CloseCommand):
                self._handle_close(command)

    def _handle_prepare(self, command: _PrepareCommand) -> None:
        try:
            wav = self._ensure_wav()
            device = self.audio_device or "default"
            with _alsa_environment(self.environment):
                if self._uses_ephemeral_playback(device):
                    self._verify_device(wav, device)
                else:
                    self._ensure_playback_pcm(wav, device)
            self._audio_device_unavailable = False
            self._missing_device_warning_logged = False
            result = True
        except (OSError, self._alsaaudio.ALSAAudioError) as exc:
            message = str(exc)
            if _is_missing_audio_device_error(message):
                self._mark_device_unavailable(message)
            else:
                LOGGER.warning(
                    "failed to prepare click PCM on %s: %s",
                    self.audio_device or "default",
                    exc,
                )
            self._clear_wav_cache()
            result = False
        command.loop.call_soon_threadsafe(command.future.set_result, result)

    def _handle_release(self, command: _ReleaseCommand) -> None:
        self._close_playback_pcm()
        self._clear_wav_cache()
        self._audio_device_unavailable = False
        self._missing_device_warning_logged = False
        command.loop.call_soon_threadsafe(command.future.set_result, None)

    def _handle_close(self, command: _CloseCommand) -> None:
        self._stop_event.set()
        self._close_playback_pcm()
        self._clear_wav_cache()
        command.loop.call_soon_threadsafe(command.future.set_result, None)

    def _process_click_queue(self) -> bool:
        had_clicks = False
        while True:
            try:
                self._click_queue.get_nowait()
            except queue.Empty:
                return had_clicks
            had_clicks = True
            if not self._write_click_once():
                self._click_queue.put_nowait(None)
                self._wake_event.set()

    def _write_click_once(self) -> bool:
        if self._audio_device_unavailable:
            return True
        for attempt in range(_MAX_WRITE_RECOVERY_ATTEMPTS):
            try:
                wav = self._ensure_wav()
                device = self.audio_device or "default"
                with _alsa_environment(self.environment):
                    if self._uses_ephemeral_playback(device):
                        self._write_ephemeral_click(wav, device)
                    else:
                        pcm = self._ensure_playback_pcm(wav, device)
                        self._write_period(pcm, wav, self._playback_period_frames)
                self._audio_device_unavailable = False
                self._missing_device_warning_logged = False
                return True
            except self._alsaaudio.ALSAAudioError as exc:
                message = str(exc)
                if _is_pcm_try_again(message) or _is_device_busy(message):
                    return False
                if _is_missing_audio_device_error(message):
                    self._mark_device_unavailable(message)
                    return True
                if (
                    _is_recoverable_alsa_pcm_error(message)
                    and attempt + 1 < _MAX_WRITE_RECOVERY_ATTEMPTS
                ):
                    LOGGER.debug("recreating ALSA PCM after %s", message)
                    self._close_playback_pcm()
                    time.sleep(0.01)
                    continue
                LOGGER.warning("ALSA click playback failed: %s", message)
                return True
            except OSError:
                LOGGER.exception("failed to play click through ALSA")
                return True
        return True

    def _mark_device_unavailable(self, message: str) -> None:
        self._audio_device_unavailable = True
        self._log_missing_device_once(message)

    def _log_missing_device_once(self, message: str) -> None:
        if self._missing_device_warning_logged:
            return
        self._missing_device_warning_logged = True
        LOGGER.warning(
            "click audio device unavailable (%s); dropping clicks until device returns",
            message,
        )

    def _uses_ephemeral_playback(self, device: str) -> bool:
        return is_wing_routing_pcm(device)

    def _verify_device(self, wav: WavPlaybackData, device: str) -> None:
        pcm = self._open_playback_pcm(wav, device)
        with contextlib.suppress(Exception):
            pcm.close()

    def _write_ephemeral_click(self, wav: WavPlaybackData, device: str) -> None:
        pcm = self._open_playback_pcm(wav, device)
        try:
            period_frames = _pcm_period_frames(pcm)
            self._write_period(pcm, wav, period_frames)
        finally:
            with contextlib.suppress(Exception):
                pcm.close()

    def _ensure_playback_pcm(self, wav: WavPlaybackData, device: str) -> Any:
        if (
            self._playback_pcm is not None
            and self._playback_device == device
            and self._configured_wav_path == self.wav_path
        ):
            return self._playback_pcm
        self._close_playback_pcm()
        pcm = self._open_playback_pcm(wav, device)
        self._playback_pcm = pcm
        self._playback_device = device
        self._playback_period_frames = _pcm_period_frames(pcm)
        return pcm

    def _close_playback_pcm(self) -> None:
        if self._playback_pcm is None:
            return
        with contextlib.suppress(Exception):
            self._playback_pcm.close()
        self._playback_pcm = None
        self._playback_device = ""
        self._playback_period_frames = _PLAYBACK_PERIOD_FRAMES

    def _write_period(self, pcm: Any, wav: WavPlaybackData, period_frames: int) -> None:
        frame_bytes = wav.channels * wav.sample_width
        if frame_bytes <= 0:
            raise ValueError("invalid WAV frame size")
        data = _build_exact_period_buffer(wav.frames, frame_bytes, period_frames)
        offset = 0
        period_bytes = period_frames * frame_bytes
        while offset < len(data):
            chunk = data[offset : offset + period_bytes]
            written = pcm.write(chunk)
            if isinstance(written, int):
                if written < 0:
                    raise self._alsaaudio.ALSAAudioError(f"PCM write failed with {written}")
                if written > 0:
                    offset += written * frame_bytes
                    continue
                time.sleep(0.001)
                continue
            offset = len(data)

    def _ensure_wav(self) -> WavPlaybackData:
        if self._wav is not None and self._configured_wav_path == self.wav_path:
            return self._wav
        wav = load_wav(self.wav_path)
        self._wav = wav
        self._configured_wav_path = self.wav_path
        return wav

    def _open_playback_pcm(self, wav: WavPlaybackData, device: str) -> Any:
        with _suppress_alsa_stderr():
            return self._alsaaudio.PCM(
                type=self._alsaaudio.PCM_PLAYBACK,
                mode=self._alsaaudio.PCM_NORMAL,
                device=device,
                channels=wav.channels,
                rate=wav.rate,
                format=_sample_width_to_format(self._alsaaudio, wav.sample_width),
                periodsize=_PLAYBACK_PERIOD_FRAMES,
                periods=4,
            )

    def _clear_wav_cache(self) -> None:
        self._wav = None
        self._configured_wav_path = ""


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


def _try_set_realtime_priority() -> None:
    scheduler = getattr(os, "SCHED_FIFO", None)
    if scheduler is None or not hasattr(os, "sched_setscheduler"):
        return
    try:
        os.sched_setscheduler(0, scheduler, os.sched_param(_CLICK_REALTIME_PRIORITY))
    except OSError:
        return


def _alsaaudio_available() -> bool:
    try:
        import alsaaudio  # noqa: F401
    except ImportError:
        return False
    return True


def _is_pcm_try_again(message: str) -> bool:
    lowered = message.casefold()
    return (
        "resource temporarily unavailable" in lowered
        or "try again" in lowered
        or "would block" in lowered
    )


def _is_device_busy(message: str) -> bool:
    return "Device or resource busy" in message or "Resource busy" in message


def _is_missing_audio_device_error(message: str) -> bool:
    lowered = message.casefold()
    return (
        "no such device" in lowered
        or "no such file" in lowered
        or "host is down" in lowered
    )


def _is_recoverable_alsa_pcm_error(message: str) -> bool:
    lowered = message.casefold()
    markers = (
        "bad state",
        "bad file descriptor",
        "invalid argument",
        "already used",
        "broken pipe",
    )
    return any(marker in lowered for marker in markers)


def _pcm_period_frames(pcm: Any) -> int:
    info = getattr(pcm, "info", None)
    if callable(info):
        try:
            data = info()
            for key in ("period_size", "periodsize"):
                period = int(data.get(key, 0))
                if period > 0:
                    return period
        except (AttributeError, TypeError, ValueError):
            pass
    return _PLAYBACK_PERIOD_FRAMES


def _build_exact_period_buffer(data: bytes, frame_bytes: int, period_frames: int) -> bytes:
    """Build one ALSA period of click audio for immediate playout on a persistent PCM.

    pyalsaaudio defers playback until a full period is written and recommends
    writes of exactly one period. Long click WAVs must be truncated so each beat
    commits one period instead of buffering partial playout across triggers.
    """

    period_bytes = period_frames * frame_bytes
    click = data[:period_bytes]
    if len(click) >= period_bytes:
        return click[:period_bytes]
    return click + bytes(period_bytes - len(click))


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
def _suppress_alsa_stderr():
    import sys

    stderr_fd = sys.stderr.fileno()
    saved = os.dup(stderr_fd)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), stderr_fd)
        yield
    finally:
        os.dup2(saved, stderr_fd)
        os.close(saved)


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
