"""Repeatable baseline evaluations."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from minxionghydrocast.models.baselines import PersistenceNowcaster, RainfallThresholdRiskScorer
from minxionghydrocast.models.metrics import binary_event_metrics, rmse

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def sample_nowcasting_case(horizon: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Create a tiny deterministic radar-like rainfall case for smoke tests."""

    input_frames = np.array(
        [
            [[0.0, 1.0], [3.0, 8.0]],
            [[0.0, 2.0], [5.0, 12.0]],
            [[0.0, 3.0], [8.0, 16.0]],
        ]
    )
    increments = np.arange(1, horizon + 1, dtype=float).reshape(horizon, 1, 1)
    target_frames = input_frames[-1] + increments * np.array([[0.0, 1.0], [2.0, 3.0]])
    return input_frames, target_frames


def evaluate_persistence_nowcaster(
    *,
    horizon: int = 3,
    event_threshold_mm: float = 10.0,
) -> dict[str, object]:
    input_frames, target_frames = sample_nowcasting_case(horizon=horizon)
    model = PersistenceNowcaster(horizon=horizon)
    prediction = model.predict(input_frames)
    event_metrics = binary_event_metrics(
        prediction >= event_threshold_mm,
        target_frames >= event_threshold_mm,
    )
    return {
        "model": "PersistenceNowcaster",
        "horizon": horizon,
        "input_shape": list(input_frames.shape),
        "target_shape": list(target_frames.shape),
        "rmse_mm": round(rmse(prediction, target_frames), 6),
        "event_threshold_mm": event_threshold_mm,
        "event_metrics": event_metrics.to_dict(),
    }


def load_threshold_events(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def bool_from_text(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "警戒", "淹水"}


def evaluate_threshold_risk(events: list[dict[str, str]]) -> dict[str, object]:
    predicted: list[bool] = []
    observed: list[bool] = []
    scored_events: list[dict[str, object]] = []

    for event in events:
        scorer = RainfallThresholdRiskScorer(
            warning_1h=float(event["warning_1h_mm"]),
            warning_3h=float(event["warning_3h_mm"]),
            warning_6h=float(event["warning_6h_mm"]),
        )
        rain_1h = float(event["rain_1h_mm"])
        rain_3h = float(event["rain_3h_mm"])
        rain_6h = float(event["rain_6h_mm"])
        score = scorer.score(rain_1h, rain_3h, rain_6h)
        label = scorer.label(rain_1h, rain_3h, rain_6h)
        predicted_event = label == "warning"
        observed_event = bool_from_text(event["observed_event"])
        predicted.append(predicted_event)
        observed.append(observed_event)
        scored_events.append(
            {
                "event_id": event["event_id"],
                "risk_score": round(score, 6),
                "predicted_label": label,
                "predicted_event": predicted_event,
                "observed_event": observed_event,
            }
        )

    event_metrics = binary_event_metrics(predicted, observed)
    return {
        "model": "RainfallThresholdRiskScorer",
        "event_count": len(events),
        "event_metrics": event_metrics.to_dict(),
        "events": scored_events,
    }


def evaluate_all(
    *,
    event_path: Path,
    horizon: int = 3,
    event_threshold_mm: float = 10.0,
) -> dict[str, object]:
    events = load_threshold_events(event_path)
    return {
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "nowcasting": evaluate_persistence_nowcaster(
            horizon=horizon,
            event_threshold_mm=event_threshold_mm,
        ),
        "flood_risk": evaluate_threshold_risk(events),
    }


def write_evaluation_result(result: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
