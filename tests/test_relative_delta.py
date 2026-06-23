import pytest

from midijuggler.modules.modifier.relative_delta import (
    absolute_delta,
    apply_relative_delta,
    mcu_relative_delta,
    offset_binary_relative_delta,
)
from midijuggler.modules.modifier.range_map import RangeMapTransform


def test_offset_binary_relative_delta() -> None:
    assert offset_binary_relative_delta(64) == 0
    assert offset_binary_relative_delta(65) == 1
    assert offset_binary_relative_delta(63) == -1


def test_mcu_relative_delta() -> None:
    assert mcu_relative_delta(64) == 0
    assert mcu_relative_delta(1) == 1
    assert mcu_relative_delta(63) == 63
    assert mcu_relative_delta(65) == -1
    assert mcu_relative_delta(127) == -63


def test_absolute_delta_wraps_7bit() -> None:
    assert absolute_delta(10, 12) == 2
    assert absolute_delta(12, 10) == -2
    assert absolute_delta(127, 1) == 2
    assert absolute_delta(1, 127) == -2
    assert absolute_delta(None, 64) == 0


def test_apply_relative_delta_mcu_encoding() -> None:
    transform = RangeMapTransform(
        input_min=1.0,
        input_max=127.0,
        output_min=0.0,
        output_max=1.0,
        invert=False,
    )
    current = 0.5
    mapped = apply_relative_delta(current, 1.0, transform, encoding="mcu")
    assert mapped == pytest.approx(0.5 + 1.0 / 63.0)
    mapped = apply_relative_delta(current, 65.0, transform, encoding="mcu")
    assert mapped == pytest.approx(0.5 - 1.0 / 63.0)


def test_apply_relative_delta_absolute_encoding() -> None:
    transform = RangeMapTransform(
        input_min=1.0,
        input_max=127.0,
        output_min=0.0,
        output_max=1.0,
        invert=False,
    )
    current = 0.5
    mapped = apply_relative_delta(
        current,
        64.0,
        transform,
        encoding="absolute_delta",
        last_value=63,
    )
    assert mapped == pytest.approx(0.5 + 1.0 / 126.0)


def test_apply_relative_delta_absolute_encoding_uses_connection_input_span() -> None:
    transform = RangeMapTransform(
        input_min=0.0,
        input_max=127.0,
        output_min=-90.0,
        output_max=10.0,
    )
    current = 0.0
    mapped = apply_relative_delta(
        current,
        64.0,
        transform,
        encoding="absolute_delta",
        last_value=63,
    )
    assert mapped == pytest.approx(100.0 / 127.0)
