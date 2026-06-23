"""Tests for range map scale curves."""

import pytest

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind
from midijuggler.modules.modifier.range_map import (
    RangeMapTransform,
    apply_range_map,
    db_to_fader_float,
    decode_log_position,
    encode_log_position,
    fader_float_to_db,
)


def test_fader_float_to_db_matches_wing_examples() -> None:
    assert fader_float_to_db(0.7) == pytest.approx(-2.0)
    assert fader_float_to_db(0.675) == pytest.approx(-3.0)
    assert fader_float_to_db(0.5) == pytest.approx(-10.0)


def test_db_to_fader_float_inverts_piecewise_law() -> None:
    for db in (-90.0, -60.0, -30.0, -10.0, 0.0, 10.0):
        assert fader_float_to_db(db_to_fader_float(db)) == pytest.approx(db, abs=1e-9)


def test_log_position_round_trip() -> None:
    for value in (0.0, 0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
        encoded = encode_log_position(value)
        assert value == pytest.approx(decode_log_position(encoded), abs=1e-9)


def test_log_to_linear_curve_is_gentler_at_quiet_fader_than_old_law() -> None:
    transform = RangeMapTransform(
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=127.0,
        scale_curve="log_to_linear",
    )
    quiet = apply_range_map(0.1, transform)
    linear = apply_range_map(0.1, RangeMapTransform())
    assert quiet < linear


def test_linear_to_log_curve_keeps_more_level_at_bottom() -> None:
    transform = RangeMapTransform(
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=127.0,
        scale_curve="linear_to_log",
    )
    low = apply_range_map(0.1, transform)
    linear = apply_range_map(0.1, RangeMapTransform())
    assert low > linear


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


def test_output_uses_fader_scale_curve_only_for_normalized_outputs() -> None:
    from midijuggler.modules.modifier.range_map import output_uses_fader_scale_curve

    assert output_uses_fader_scale_curve(
        RangeMapTransform(output_min=0.0, output_max=1.0)
    )
    assert not output_uses_fader_scale_curve(
        RangeMapTransform(output_min=-90.0, output_max=10.0)
    )


def test_encode_wing_fader_wire_normalized_range() -> None:
    from midijuggler.modules.modifier.range_map import encode_wing_fader_wire

    wire, raw = encode_wing_fader_wire(0.25, output_min=0.0, output_max=1.0)
    assert wire == pytest.approx(0.25)
    assert raw is True

    wire, raw = encode_wing_fader_wire(-5.873, output_min=0.0, output_max=1.0)
    assert wire == pytest.approx(db_to_fader_float(-5.873))
    assert raw is True


def test_encode_wing_fader_wire_engineering_db_range() -> None:
    from midijuggler.modules.modifier.range_map import encode_wing_fader_wire

    wire, raw = encode_wing_fader_wire(-5.873, output_min=-90.0, output_max=10.0)
    assert wire == pytest.approx(-5.873)
    assert raw is False

    wire, raw = encode_wing_fader_wire(0.476, output_min=-90.0, output_max=10.0)
    assert wire == pytest.approx(0.476)
    assert raw is False


def test_decode_wing_fader_feedback_engineering_range() -> None:
    from midijuggler.modules.modifier.range_map import decode_wing_fader_feedback

    wire = db_to_fader_float(0.476)
    assert decode_wing_fader_feedback(
        wire,
        output_min=-90.0,
        output_max=10.0,
        wire_raw=True,
    ) == pytest.approx(0.476, abs=0.05)
    assert decode_wing_fader_feedback(
        0.476,
        output_min=-90.0,
        output_max=10.0,
        wire_raw=False,
    ) == pytest.approx(0.476)


def test_decode_wing_fader_feedback_normalized_range() -> None:
    from midijuggler.modules.modifier.range_map import decode_wing_fader_feedback

    assert decode_wing_fader_feedback(
        0.25,
        output_min=0.0,
        output_max=1.0,
        wire_raw=True,
    ) == pytest.approx(0.25)
    assert decode_wing_fader_feedback(
        -5.873,
        output_min=0.0,
        output_max=1.0,
        wire_raw=False,
    ) == pytest.approx(db_to_fader_float(-5.873))


def test_encode_wing_fader_wire_fallback_without_range() -> None:
    from midijuggler.modules.modifier.range_map import encode_wing_fader_wire

    wire, raw = encode_wing_fader_wire(0.25)
    assert wire == pytest.approx(0.25)
    assert raw is True

    wire, raw = encode_wing_fader_wire(-5.873)
    assert wire == pytest.approx(db_to_fader_float(-5.873))
    assert raw is True
