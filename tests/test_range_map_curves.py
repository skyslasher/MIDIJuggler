"""Tests for range map scale curves."""

import pytest

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind
from midijuggler.modules.modifier.range_map import (
    RangeMapTransform,
    apply_range_map,
    decode_log_position,
    encode_log_position,
)


def test_log_position_round_trip() -> None:
    for value in (0.0, 0.01, 0.1, 0.5, 0.9, 1.0):
        encoded = encode_log_position(value)
        assert value == pytest.approx(decode_log_position(encoded), abs=1e-9)


def test_log_to_linear_curve_maps_quiet_fader_higher() -> None:
    transform = RangeMapTransform(
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=127.0,
        scale_curve="log_to_linear",
    )
    low = apply_range_map(0.1, transform)
    linear = apply_range_map(0.1, RangeMapTransform())
    assert low > linear


def test_linear_to_log_curve_maps_quiet_encoder_lower() -> None:
    transform = RangeMapTransform(
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=127.0,
        scale_curve="linear_to_log",
    )
    low = apply_range_map(0.1, transform)
    linear = apply_range_map(0.1, RangeMapTransform())
    assert low < linear


def test_range_map_reads_scale_curve_from_connection() -> None:
    connection = ConnectionSpec(
        id="test",
        source="a.x",
        target="b.y",
        modifier=ModifierKind.RANGE_MAP,
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=127.0,
        scale_curve="log_to_linear",
    )
    transform = RangeMapTransform.from_connection(connection)
    assert transform.scale_curve == "log_to_linear"
