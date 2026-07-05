import numpy as np

from floodcasttw.models.baselines import PersistenceNowcaster, RainfallThresholdRiskScorer


def test_persistence_nowcaster_repeats_latest_frame():
    frames = np.arange(3 * 2 * 2).reshape(3, 2, 2)
    prediction = PersistenceNowcaster(horizon=4).predict(frames)

    assert prediction.shape == (4, 2, 2)
    assert np.array_equal(prediction[0], frames[-1])
    assert np.array_equal(prediction[-1], frames[-1])


def test_threshold_scorer_labels_watch_before_warning():
    scorer = RainfallThresholdRiskScorer(warning_1h=50, warning_3h=100, warning_6h=150)

    assert scorer.label(10, 20, 30) == "normal"
    assert scorer.label(40, 20, 30) == "watch"
    assert scorer.label(50, 20, 30) == "warning"
