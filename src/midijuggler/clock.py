"""MIDI clock BPM tracking."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import fmean

MIDI_CLOCK_TICKS_PER_QUARTER = 24

CLICK_INTERVALS = ("sixteenth", "eighth", "quarter", "half", "whole")


@dataclass
class ClockBpmTracker:
    """Estimate BPM from MIDI timing clock ticks."""

    smoothing_ticks: int = 48
    timeout_seconds: float = 2.0
    _tick_times: deque[float] = field(init=False)
    _last_bpm: float | None = None

    def __post_init__(self) -> None:
        if self.smoothing_ticks < 2:
            raise ValueError("smoothing_ticks must be >= 2")
        self._tick_times = deque(maxlen=self.smoothing_ticks)

    @property
    def bpm(self) -> float | None:
        return self._last_bpm

    def reset(self) -> None:
        self._tick_times.clear()
        self._last_bpm = None

    def tick(self, timestamp: float) -> float | None:
        """Record one MIDI clock tick and return the current BPM estimate."""

        if self._tick_times and timestamp - self._tick_times[-1] > self.timeout_seconds:
            self.reset()

        self._tick_times.append(timestamp)
        if len(self._tick_times) < 2:
            return None

        intervals = [
            later - earlier
            for earlier, later in zip(self._tick_times, list(self._tick_times)[1:])
            if later > earlier
        ]
        if not intervals:
            return None

        seconds_per_tick = fmean(intervals)
        if seconds_per_tick <= 0:
            return None

        self._last_bpm = 60.0 / (seconds_per_tick * MIDI_CLOCK_TICKS_PER_QUARTER)
        return self._last_bpm
