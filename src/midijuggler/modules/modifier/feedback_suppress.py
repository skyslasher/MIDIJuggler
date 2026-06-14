"""Suppress desk feedback while a paired encoder is being turned."""

from __future__ import annotations

import re
import time

DEFAULT_FEEDBACK_SUPPRESS_MS = 500

_ENCODER_TURN_PATTERN = re.compile(
    r"^(?P<module>[^.]+)\.(?P<layer>layer_[ab])_encoder_(?P<num>\d+)_turn$"
)
_ENCODER_FEEDBACK_PATTERN = re.compile(
    r"^(?P<module>[^.]+)\.(?P<layer>layer_[ab])_encoder_(?P<num>\d+)_(?:value|led_ring)$"
)


def parse_feedback_suppress_ms(
    value: object,
    *,
    default: int = DEFAULT_FEEDBACK_SUPPRESS_MS,
) -> int:
    if value is None:
        return default
    try:
        window_ms = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("feedback_suppress_ms must be an integer") from exc
    if window_ms < 0:
        raise ValueError("feedback_suppress_ms must be >= 0")
    if window_ms > 10000:
        raise ValueError("feedback_suppress_ms must be <= 10000")
    return window_ms


def encoder_control_group(point_id: str) -> str | None:
    turn_match = _ENCODER_TURN_PATTERN.match(point_id)
    if turn_match is not None:
        return (
            f"{turn_match.group('module')}."
            f"{turn_match.group('layer')}_encoder_{turn_match.group('num')}"
        )
    feedback_match = _ENCODER_FEEDBACK_PATTERN.match(point_id)
    if feedback_match is not None:
        return (
            f"{feedback_match.group('module')}."
            f"{feedback_match.group('layer')}_encoder_{feedback_match.group('num')}"
        )
    return None


class EncoderFeedbackSuppressor:
    """Pause desk-to-controller feedback shortly after encoder movement."""

    def __init__(self, window_ms: int = DEFAULT_FEEDBACK_SUPPRESS_MS) -> None:
        self._window_seconds = 0.0
        self._last_turn_at: dict[str, float] = {}
        self.configure(window_ms)

    @property
    def enabled(self) -> bool:
        return self._window_seconds > 0.0

    def configure(self, window_ms: int) -> None:
        self._window_seconds = max(0.0, window_ms) / 1000.0
        if not self.enabled:
            self._last_turn_at.clear()

    def note_turn(self, source_point_id: str, *, now: float | None = None) -> None:
        if not self.enabled:
            return
        group = encoder_control_group(source_point_id)
        if group is None:
            return
        timestamp = time.monotonic() if now is None else now
        self._last_turn_at[group] = timestamp

    def should_suppress_target(self, target_point_id: str, *, now: float | None = None) -> bool:
        if not self.enabled:
            return False
        group = encoder_control_group(target_point_id)
        if group is None:
            return False
        last_turn = self._last_turn_at.get(group)
        if last_turn is None:
            return False
        timestamp = time.monotonic() if now is None else now
        return timestamp - last_turn <= self._window_seconds
