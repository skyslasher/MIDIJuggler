"""Tests for data-point float comparison helpers."""

import pytest

from midijuggler.datapoint.compare import compare_epsilon, float_values_differ
from midijuggler.datapoint.types import DataPointId, DataPointSpec, ValueType


def test_compare_epsilon_scales_with_value_span() -> None:
    spec = DataPointSpec(
        id=DataPointId("wing", "/ch/1/fdr"),
        value_type=ValueType.FLOAT,
        direction="bidirectional",
        value_min=-144.0,
        value_max=10.0,
    )
    assert compare_epsilon(spec) == pytest.approx(0.0154, abs=0.0001)


def test_float_values_differ_respects_spec_epsilon() -> None:
    spec = DataPointSpec(
        id=DataPointId("wing", "/ch/1/fdr"),
        value_type=ValueType.FLOAT,
        direction="bidirectional",
        value_min=-144.0,
        value_max=10.0,
    )
    assert float_values_differ(0.0, 0.01, spec) is False
    assert float_values_differ(0.0, 0.02, spec) is True
