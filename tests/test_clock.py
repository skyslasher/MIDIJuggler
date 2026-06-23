import pytest

from midijuggler.clock import ClockBpmTracker


def test_clock_tracker_estimates_bpm_from_midi_ticks() -> None:
    tracker = ClockBpmTracker(smoothing_ticks=24)
    interval = 60.0 / (120.0 * 24.0)

    bpm = None
    for tick in range(24):
        bpm = tracker.tick(tick * interval)

    assert bpm == pytest.approx(120.0)
    assert tracker.bpm == pytest.approx(120.0)


def test_clock_tracker_resets_after_timeout() -> None:
    tracker = ClockBpmTracker(smoothing_ticks=4, timeout_seconds=1.0)
    tracker.tick(0.0)
    assert tracker.tick(0.02) is not None

    assert tracker.tick(2.0) is None
    assert tracker.bpm is None


def test_clock_tracker_requires_at_least_two_smoothing_ticks() -> None:
    with pytest.raises(ValueError, match="smoothing_ticks"):
        ClockBpmTracker(smoothing_ticks=1)
