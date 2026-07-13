import numpy as np

from minxionghydrocast.models.metrics import binary_event_metrics, rmse


def test_rmse_matches_expected_value():
    prediction = np.array([1.0, 2.0, 3.0])
    target = np.array([1.0, 4.0, 5.0])

    assert round(rmse(prediction, target), 6) == 1.632993


def test_binary_event_metrics_counts_and_scores():
    metrics = binary_event_metrics(
        predicted=[True, True, False, False],
        observed=[True, False, True, False],
    )

    assert metrics.hits == 1
    assert metrics.misses == 1
    assert metrics.false_alarms == 1
    assert metrics.correct_negatives == 1
    assert metrics.to_dict()["csi"] == 0.333333
    assert metrics.to_dict()["pod"] == 0.5
    assert metrics.to_dict()["far"] == 0.5
