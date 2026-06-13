"""Range mapping transform."""

from __future__ import annotations

from dataclasses import dataclass

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind


@dataclass(frozen=True)
class RangeMapTransform:
    input_min: float = 0.0
    input_max: float = 1.0
    output_min: float = 0.0
    output_max: float = 127.0
    invert: bool = False

    @classmethod
    def from_connection(cls, connection: ConnectionSpec) -> RangeMapTransform:
        if connection.modifier != ModifierKind.RANGE_MAP:
            raise ValueError(f"unsupported modifier: {connection.modifier}")
        return cls(
            input_min=connection.input_min,
            input_max=connection.input_max,
            output_min=connection.output_min,
            output_max=connection.output_max,
            invert=connection.invert,
        )


def apply_range_map(value: float, transform: RangeMapTransform) -> float:
    if transform.input_min == transform.input_max:
        raise ValueError("range map input range must not be empty")
    clamped = min(max(value, transform.input_min), transform.input_max)
    position = (clamped - transform.input_min) / (transform.input_max - transform.input_min)
    if transform.invert:
        position = 1.0 - position
    return transform.output_min + position * (transform.output_max - transform.output_min)
