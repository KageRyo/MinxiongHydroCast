"""Evaluation metrics for rainfall nowcasting and flood-risk events."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def rmse(prediction, target) -> float:
    prediction_array = np.asarray(prediction, dtype=float)
    target_array = np.asarray(target, dtype=float)
    if prediction_array.shape != target_array.shape:
        raise ValueError(
            f"prediction and target shapes differ: {prediction_array.shape} != {target_array.shape}"
        )
    return float(np.sqrt(np.mean((prediction_array - target_array) ** 2)))


@dataclass(frozen=True)
class BinaryEventMetrics:
    hits: int
    misses: int
    false_alarms: int
    correct_negatives: int

    @property
    def csi(self) -> float:
        denominator = self.hits + self.misses + self.false_alarms
        return self.hits / denominator if denominator else 0.0

    @property
    def pod(self) -> float:
        denominator = self.hits + self.misses
        return self.hits / denominator if denominator else 0.0

    @property
    def far(self) -> float:
        denominator = self.hits + self.false_alarms
        return self.false_alarms / denominator if denominator else 0.0

    def to_dict(self) -> dict[str, float | int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "false_alarms": self.false_alarms,
            "correct_negatives": self.correct_negatives,
            "csi": round(self.csi, 6),
            "pod": round(self.pod, 6),
            "far": round(self.far, 6),
        }


def binary_event_metrics(predicted, observed) -> BinaryEventMetrics:
    predicted_array = np.asarray(predicted, dtype=bool)
    observed_array = np.asarray(observed, dtype=bool)
    if predicted_array.shape != observed_array.shape:
        raise ValueError(
            "predicted and observed shapes differ: "
            f"{predicted_array.shape} != {observed_array.shape}"
        )
    hits = int(np.logical_and(predicted_array, observed_array).sum())
    misses = int(np.logical_and(~predicted_array, observed_array).sum())
    false_alarms = int(np.logical_and(predicted_array, ~observed_array).sum())
    correct_negatives = int(np.logical_and(~predicted_array, ~observed_array).sum())
    return BinaryEventMetrics(hits, misses, false_alarms, correct_negatives)
