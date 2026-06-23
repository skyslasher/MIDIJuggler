"""Range mapping transform."""

from __future__ import annotations

import math
from dataclasses import dataclass

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind, SCALE_CURVES

_LOG_RATIO = 9.0


@dataclass(frozen=True)
class RangeMapTransform:
    input_min: float = 0.0
    input_max: float = 1.0
    output_min: float = 0.0
    output_max: float = 127.0
    invert: bool = False
    scale_curve: str = "linear"

    @classmethod
    def from_connection(cls, connection: ConnectionSpec) -> RangeMapTransform:
        if connection.modifier != ModifierKind.RANGE_MAP:
            raise ValueError(f"unsupported modifier: {connection.modifier}")
        scale_curve = connection.scale_curve
        if scale_curve not in SCALE_CURVES:
            raise ValueError(f"unsupported scale_curve: {scale_curve!r}")
        return cls(
            input_min=connection.input_min,
            input_max=connection.input_max,
            output_min=connection.output_min,
            output_max=connection.output_max,
            invert=connection.invert,
            scale_curve=scale_curve,
        )


def decode_log_position(value: float) -> float:
    """Map a logarithmic 0..1 control value to a linear 0..1 position."""

    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return math.log10(1.0 + value * _LOG_RATIO)


def encode_log_position(value: float) -> float:
    """Map a linear 0..1 position to a logarithmic 0..1 control value."""

    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return (math.pow(10.0, value) - 1.0) / _LOG_RATIO


def apply_range_map(value: float, transform: RangeMapTransform) -> float:
    if transform.input_min == transform.input_max:
        raise ValueError("range map input range must not be empty")
    clamped = min(max(value, transform.input_min), transform.input_max)
    position = (clamped - transform.input_min) / (transform.input_max - transform.input_min)
    if transform.scale_curve == "log_to_linear":
        position = decode_log_position(position)
    if transform.invert:
        position = 1.0 - position
    if transform.scale_curve == "linear_to_log":
        position = encode_log_position(position)
    return transform.output_min + position * (transform.output_max - transform.output_min)
