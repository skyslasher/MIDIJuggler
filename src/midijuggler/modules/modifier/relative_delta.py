"""Apply relative MIDI encoder deltas to absolute target values."""

from __future__ import annotations

from midijuggler.modules.modifier.range_map import RangeMapTransform

ENCODING_OFFSET_BINARY = "offset_binary"
ENCODING_MCU = "mcu"
ENCODING_ABSOLUTE_DELTA = "absolute_delta"
DEFAULT_RELATIVE_ENCODING = ENCODING_OFFSET_BINARY


def relative_cc_delta(value: float, *, encoding: str = ENCODING_OFFSET_BINARY) -> int:
    step = int(round(value))
    if encoding == ENCODING_MCU:
        return mcu_relative_delta(step)
    if encoding == ENCODING_ABSOLUTE_DELTA:
        raise ValueError("absolute_delta requires the previous CC value")
    return offset_binary_relative_delta(step)


def offset_binary_relative_delta(step: int) -> int:
    if step == 64:
        return 0
    return step - 64


def mcu_relative_delta(step: int) -> int:
    """Mackie/MCU V-Pot encoding: 1-63 = CW, 65-127 = CCW."""

    if step == 64:
        return 0
    if step > 64:
        return -(step - 64)
    return step


def absolute_delta(last_step: int | None, step: int) -> int:
    """Delta between successive absolute encoder positions with 7-bit wrap."""

    if last_step is None:
        return 0
    delta = step - last_step
    if delta > 64:
        delta -= 128
    elif delta < -64:
        delta += 128
    return delta


def apply_relative_steps(
    current: float,
    delta_steps: int,
    transform: RangeMapTransform,
    *,
    encoding: str = ENCODING_OFFSET_BINARY,
) -> float | None:
    if delta_steps == 0:
        return None
    if transform.invert:
        delta_steps = -delta_steps
    span = transform.output_max - transform.output_min
    input_span = transform.input_max - transform.input_min
    if input_span <= 0:
        raise ValueError("range map input range must not be empty")
    if encoding in {ENCODING_OFFSET_BINARY, ENCODING_MCU}:
        # Standard relative encoders: 64 detents per revolution.
        step_size = span / 63.0
    else:
        # Absolute encoder positions: one CC tick spans one connection input unit.
        step_size = span / input_span
    next_value = current + delta_steps * step_size
    return min(max(next_value, transform.output_min), transform.output_max)


def apply_relative_delta(
    current: float,
    value: float,
    transform: RangeMapTransform,
    *,
    encoding: str = ENCODING_OFFSET_BINARY,
    last_value: int | None = None,
) -> float | None:
    step = int(round(value))
    if encoding == ENCODING_ABSOLUTE_DELTA:
        delta_steps = absolute_delta(last_value, step)
    else:
        delta_steps = relative_cc_delta(value, encoding=encoding)
    return apply_relative_steps(current, delta_steps, transform, encoding=encoding)
