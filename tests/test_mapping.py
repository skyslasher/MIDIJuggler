import pytest

from midijuggler.events import ControlEvent
from midijuggler.mapping import MappingEngine, MappingRule


def test_linear_mapping_scales_and_clamps_values() -> None:
    rule = MappingRule(
        id="expression",
        source="gpio:pin17",
        target="midi:cc:1:11",
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=127.0,
    )

    assert rule.apply(0.5) == pytest.approx(63.5)
    assert rule.apply(-1.0) == pytest.approx(0.0)
    assert rule.apply(2.0) == pytest.approx(127.0)


def test_inverted_mapping_reverses_output_position() -> None:
    rule = MappingRule(
        id="inverted",
        source="osc:/pedal",
        target="rtp_midi:cc:1:74",
        input_min=0.0,
        input_max=1.0,
        output_min=0.0,
        output_max=100.0,
        invert=True,
    )

    assert rule.apply(0.25) == pytest.approx(75.0)


def test_engine_maps_only_matching_sources() -> None:
    engine = MappingEngine(
        [
            MappingRule(id="match", source="gpio:pin17", target="midi:cc:1:64"),
            MappingRule(id="miss", source="gpio:pin27", target="midi:cc:1:65"),
        ]
    )

    mapped = engine.map_event(ControlEvent(source="gpio", control="pin17", value=1.0))

    assert len(mapped) == 1
    assert mapped[0].mapping_id == "match"
    assert mapped[0].value == pytest.approx(127.0)


def test_mapping_rejects_empty_input_range() -> None:
    with pytest.raises(ValueError, match="empty input range"):
        MappingRule(
            id="bad",
            source="gpio:pin17",
            target="midi:cc:1:64",
            input_min=1.0,
            input_max=1.0,
        )
