import numpy as np
import pytest

from minxionghydrocast.models.baselines import (
    OpticalFlowNowcaster,
    PersistenceNowcaster,
    RainfallThresholdRiskScorer,
    estimate_translation,
)


def translated(frame: np.ndarray, row_shift: int, column_shift: int) -> np.ndarray:
    output = np.zeros_like(frame)
    height, width = frame.shape
    source_row_start = max(0, -row_shift)
    source_row_end = min(height, height - row_shift)
    source_column_start = max(0, -column_shift)
    source_column_end = min(width, width - column_shift)
    if source_row_start >= source_row_end or source_column_start >= source_column_end:
        return output
    output[
        source_row_start + row_shift : source_row_end + row_shift,
        source_column_start + column_shift : source_column_end + column_shift,
    ] = frame[source_row_start:source_row_end, source_column_start:source_column_end]
    return output


def test_persistence_nowcaster_repeats_latest_frame():
    frames = np.arange(3 * 2 * 2).reshape(3, 2, 2)
    prediction = PersistenceNowcaster(horizon=4).predict(frames)

    assert prediction.shape == (4, 2, 2)
    assert np.array_equal(prediction[0], frames[-1])
    assert np.array_equal(prediction[-1], frames[-1])


@pytest.mark.parametrize("shift", [(0, 3), (2, -2), (-3, 1)])
def test_optical_flow_estimates_translation_direction(shift):
    reference = np.zeros((40, 40), dtype=np.float32)
    reference[10:16, 8:13] = 45.0
    reference[23:27, 27:31] = 20.0
    moving = translated(reference, *shift)

    assert estimate_translation(
        reference,
        moving,
        max_displacement=8,
        min_valid_pixels=8,
    ) == shift


def test_optical_flow_ignores_missing_pixels():
    reference = np.zeros((40, 40), dtype=np.float32)
    reference[10:16, 8:13] = 45.0
    reference[23:27, 27:31] = 20.0
    moving = translated(reference, 2, -2)
    reference_mask = np.ones_like(reference, dtype=bool)
    moving_mask = np.ones_like(moving, dtype=bool)
    reference_mask[:8, :8] = False
    moving_mask[:8, :8] = False

    assert estimate_translation(
        reference,
        moving,
        reference_mask=reference_mask,
        moving_mask=moving_mask,
        max_displacement=8,
        min_valid_pixels=8,
    ) == (2, -2)


def test_optical_flow_stationary_and_empty_precipitation_have_zero_motion():
    stationary = np.zeros((32, 32), dtype=np.float32)
    stationary[12:17, 13:19] = 35.0

    assert estimate_translation(stationary, stationary, min_valid_pixels=4) == (0, 0)
    assert estimate_translation(
        np.zeros_like(stationary),
        np.zeros_like(stationary),
        min_valid_pixels=4,
    ) == (0, 0)


def test_optical_flow_predicts_future_translations_without_wraparound():
    first = np.zeros((40, 40), dtype=np.float32)
    first[10:16, 8:13] = 45.0
    frames = np.stack(
        [first, translated(first, 0, 2), translated(first, 0, 4)],
        axis=0,
    )

    prediction = OpticalFlowNowcaster(
        horizon=2,
        max_displacement=8,
        min_valid_pixels=8,
    ).predict(frames)

    np.testing.assert_array_equal(prediction[0], translated(first, 0, 6))
    np.testing.assert_array_equal(prediction[1], translated(first, 0, 8))


def test_threshold_scorer_labels_watch_before_warning():
    scorer = RainfallThresholdRiskScorer(warning_1h=50, warning_3h=100, warning_6h=150)

    assert scorer.label(10, 20, 30) == "normal"
    assert scorer.label(40, 20, 30) == "watch"
    assert scorer.label(50, 20, 30) == "warning"
