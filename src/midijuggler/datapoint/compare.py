"""Shared float comparison helpers for data-point values."""

from __future__ import annotations

from midijuggler.datapoint.types import DataPointSpec


def compare_epsilon(spec: DataPointSpec | None) -> float:
    if spec is None or spec.value_min is None or spec.value_max is None:
        return 1e-9
    span = float(spec.value_max) - float(spec.value_min)
    if span > 10.0:
        return max(0.001, span * 1e-4)
    if span > 1.0:
        return max(1e-6, span * 1e-5)
    return 1e-9


def float_values_differ(
    previous: float,
    current: float,
    spec: DataPointSpec | None,
) -> bool:
    return abs(current - previous) > compare_epsilon(spec)
