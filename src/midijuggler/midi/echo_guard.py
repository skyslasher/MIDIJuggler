"""Suppress MIDI input that matches recently sent output (loopback echo)."""

from __future__ import annotations

import time

DEFAULT_ECHO_GUARD_MS = 30


def parse_echo_guard_ms(value: object, *, default: int = DEFAULT_ECHO_GUARD_MS) -> int:
    if value is None:
        return default
    try:
        window_ms = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("echo_guard_ms must be an integer") from exc
    if window_ms < 0:
        raise ValueError("echo_guard_ms must be >= 0")
    if window_ms > 5000:
        raise ValueError("echo_guard_ms must be <= 5000")
    return window_ms


def midi_message_key(status: int, data: tuple[int, ...]) -> tuple[int, tuple[int, ...]]:
    return (status & 0xFF, tuple(byte & 0x7F for byte in data))


class MidiEchoGuard:
    """Track recent MIDI output and treat matching input as hardware echo."""

    def __init__(self, window_ms: int = DEFAULT_ECHO_GUARD_MS) -> None:
        self._window_seconds = 0.0
        self._recent: list[tuple[tuple[int, tuple[int, ...]], float]] = []
        self.configure(window_ms)

    @property
    def enabled(self) -> bool:
        return self._window_seconds > 0.0

    def configure(self, window_ms: int) -> None:
        self._window_seconds = max(0.0, window_ms) / 1000.0
        if not self.enabled:
            self._recent.clear()

    def record(self, status: int, data: tuple[int, ...], *, now: float | None = None) -> None:
        if not self.enabled:
            return
        timestamp = time.monotonic() if now is None else now
        self._recent.append((midi_message_key(status, data), timestamp))
        self._prune(timestamp)

    def is_echo(self, status: int, data: tuple[int, ...], *, now: float | None = None) -> bool:
        if not self.enabled:
            return False
        timestamp = time.monotonic() if now is None else now
        self._prune(timestamp)
        key = midi_message_key(status, data)
        return any(
            recent_key == key and timestamp - sent_at <= self._window_seconds
            for recent_key, sent_at in self._recent
        )

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        if not self._recent:
            return
        self._recent = [
            (message_key, sent_at)
            for message_key, sent_at in self._recent
            if sent_at >= cutoff
        ]
