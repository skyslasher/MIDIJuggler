"""Apply relative MIDI encoder deltas to absolute target values."""

from __future__ import annotations

from midijuggler.modules.modifier.range_map import RangeMapTransform


def relative_cc_delta(value: float) -> int:
    step = int(round(value))
    if step == 64:
        return 0
    return step - 64


def apply_relative_delta(
    current: float,
    value: float,
    transform: RangeMapTransform,
) -> float | None:
    delta_steps = relative_cc_delta(value)
    if delta_steps == 0:
        return None
    if transform.invert:
        delta_steps = -delta_steps
    span = transform.output_max - transform.output_min
    step_size = span / 63.0
    next_value = current + delta_steps * step_size
    return min(max(next_value, transform.output_min), transform.output_max)
