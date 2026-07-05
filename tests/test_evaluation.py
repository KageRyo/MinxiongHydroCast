from floodcasttw.models.evaluation import (
    evaluate_persistence_nowcaster,
    evaluate_threshold_risk,
    sample_nowcasting_case,
)


def test_sample_nowcasting_case_shapes():
    inputs, targets = sample_nowcasting_case(horizon=4)

    assert inputs.shape == (3, 2, 2)
    assert targets.shape == (4, 2, 2)


def test_evaluate_persistence_nowcaster_reports_metrics():
    result = evaluate_persistence_nowcaster(horizon=3, event_threshold_mm=10.0)

    assert result["model"] == "PersistenceNowcaster"
    assert result["rmse_mm"] == 4.041452
    assert result["event_metrics"]["csi"] == 0.5


def test_evaluate_threshold_risk_reports_event_metrics():
    result = evaluate_threshold_risk(
        [
            {
                "event_id": "hit",
                "rain_1h_mm": "50",
                "rain_3h_mm": "0",
                "rain_6h_mm": "0",
                "warning_1h_mm": "50",
                "warning_3h_mm": "100",
                "warning_6h_mm": "150",
                "observed_event": "true",
            },
            {
                "event_id": "correct_negative",
                "rain_1h_mm": "0",
                "rain_3h_mm": "0",
                "rain_6h_mm": "0",
                "warning_1h_mm": "50",
                "warning_3h_mm": "100",
                "warning_6h_mm": "150",
                "observed_event": "false",
            },
        ]
    )

    assert result["model"] == "RainfallThresholdRiskScorer"
    assert result["event_metrics"]["hits"] == 1
    assert result["event_metrics"]["correct_negatives"] == 1
    assert result["events"][0]["predicted_label"] == "warning"
