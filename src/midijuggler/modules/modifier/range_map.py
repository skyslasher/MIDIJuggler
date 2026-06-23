"""Range mapping transform."""

from __future__ import annotations

import math
from dataclasses import dataclass

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind, SCALE_CURVES

# Behringer Wing / X32 normalized fader law: piecewise-linear dB segments.
_MIN_FADER_DB = -90.0
_MAX_FADER_DB = 10.0
_MIN_FADER_AMP = math.pow(10.0, _MIN_FADER_DB / 20.0)
_MAX_FADER_AMP = math.pow(10.0, _MAX_FADER_DB / 20.0)
_AMP_SPAN = _MAX_FADER_AMP - _MIN_FADER_AMP


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


def fader_float_to_db(value: float) -> float:
    """Convert a Wing/X32 normalized fader value to dB."""

    if value <= 0.0:
        return _MIN_FADER_DB
    if value >= 1.0:
        return _MAX_FADER_DB
    if value >= 0.5:
        return value * 40.0 - 30.0
    if value >= 0.25:
        return value * 80.0 - 50.0
    if value >= 0.0625:
        return value * 160.0 - 70.0
    return value * 480.0 - 90.0


def db_to_fader_float(db: float) -> float:
    """Convert dB to a Wing/X32 normalized fader value."""

    if db <= _MIN_FADER_DB:
        return 0.0
    if db >= _MAX_FADER_DB:
        return 1.0
    if db < -60.0:
        return (db + 90.0) / 480.0
    if db < -30.0:
        return (db + 70.0) / 160.0
    if db < -10.0:
        return (db + 50.0) / 80.0
    return (db + 30.0) / 40.0


def decode_log_position(value: float) -> float:
    """Map a desk log fader (0..1) to a linear amplitude position (0..1)."""

    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    amplitude = math.pow(10.0, fader_float_to_db(value) / 20.0)
    return (amplitude - _MIN_FADER_AMP) / _AMP_SPAN


def encode_log_position(value: float) -> float:
    """Map a linear amplitude position (0..1) to a desk log fader (0..1)."""

    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    amplitude = _MIN_FADER_AMP + value * _AMP_SPAN
    db = 20.0 * math.log10(amplitude)
    return db_to_fader_float(db)


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
