"""Suppress desk feedback while a paired control is being moved."""

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
_FADER_PATTERN = re.compile(
    r"^(?P<module>[^.]+)\.(?P<layer>layer_[ab])_fader(?:_(?P<num>\d+))?$"
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


def fader_control_group(point_id: str) -> str | None:
    match = _FADER_PATTERN.match(point_id)
    if match is None:
        return None
    num = match.group("num")
    suffix = f"_fader_{num}" if num is not None else "_fader"
    return f"{match.group('module')}.{match.group('layer')}{suffix}"


def control_group(point_id: str) -> str | None:
    group = encoder_control_group(point_id)
    if group is not None:
        return group
    return fader_control_group(point_id)


def reciprocal_feedback_pairs(
    connections: list[object],
) -> dict[str, str]:
    """Map desk feedback sources to their paired user-side sources."""
    pairs: dict[str, str] = {}
    for left in connections:
        left_source = getattr(left, "source", None)
        left_target = getattr(left, "target", None)
        if not isinstance(left_source, str) or not isinstance(left_target, str):
            continue
        for right in connections:
            right_source = getattr(right, "source", None)
            right_target = getattr(right, "target", None)
            if not isinstance(right_source, str) or not isinstance(right_target, str):
                continue
            if left_source == right_target and left_target == right_source:
                pairs[left_source] = right_source
    return pairs


class FeedbackSuppressor:
    """Pause desk-to-controller feedback shortly after local user input."""

    def __init__(self, window_ms: int = DEFAULT_FEEDBACK_SUPPRESS_MS) -> None:
        self._window_seconds = 0.0
        self._last_turn_at: dict[str, float] = {}
        self._last_user_input_at: dict[str, float] = {}
        self._last_outbound_target_at: dict[str, float] = {}
        self._feedback_pairs: dict[str, str] = {}
        self.configure(window_ms)

    @property
    def enabled(self) -> bool:
        return self._window_seconds > 0.0

    def configure(self, window_ms: int) -> None:
        self._window_seconds = max(0.0, window_ms) / 1000.0
        if not self.enabled:
            self._last_turn_at.clear()
            self._last_user_input_at.clear()
            self._last_outbound_target_at.clear()

    def set_feedback_pairs(self, pairs: dict[str, str]) -> None:
        self._feedback_pairs = dict(pairs)

    def note_turn(self, source_point_id: str, *, now: float | None = None) -> None:
        if not self.enabled:
            return
        group = control_group(source_point_id)
        if group is None:
            return
        timestamp = time.monotonic() if now is None else now
        self._last_turn_at[group] = timestamp

    def note_user_input(self, source_point_id: str, *, now: float | None = None) -> None:
        if not self.enabled:
            return
        timestamp = time.monotonic() if now is None else now
        self._last_user_input_at[source_point_id] = timestamp
        self.note_turn(source_point_id, now=timestamp)

    def note_outbound_target(self, target_point_id: str, *, now: float | None = None) -> None:
        if not self.enabled:
            return
        timestamp = time.monotonic() if now is None else now
        self._last_outbound_target_at[target_point_id] = timestamp

    def should_suppress_source(self, source_point_id: str, *, now: float | None = None) -> bool:
        if not self.enabled:
            return False
        timestamp = time.monotonic() if now is None else now
        last_outbound = self._last_outbound_target_at.get(source_point_id)
        if (
            last_outbound is not None
            and timestamp - last_outbound <= self._window_seconds
        ):
            return True
        user_source = self._feedback_pairs.get(source_point_id)
        if user_source is None:
            return False
        last_input = self._last_user_input_at.get(user_source)
        if last_input is None:
            return False
        return timestamp - last_input <= self._window_seconds

    def should_suppress_target(self, target_point_id: str, *, now: float | None = None) -> bool:
        if not self.enabled:
            return False
        group = control_group(target_point_id)
        if group is None:
            return False
        last_turn = self._last_turn_at.get(group)
        if last_turn is None:
            return False
        timestamp = time.monotonic() if now is None else now
        return timestamp - last_turn <= self._window_seconds


EncoderFeedbackSuppressor = FeedbackSuppressor
