"""Baseline models that are useful before deep-learning training is justified."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class ArrayLike(Protocol):
    @property
    def shape(self) -> tuple[int, ...]:
        ...


@dataclass(frozen=True)
class PersistenceNowcaster:
    """Repeat the latest radar/rainfall frame for every future step."""

    horizon: int = 6

    def predict(self, frames: ArrayLike) -> np.ndarray:
        array = np.asarray(frames)
        if array.ndim < 3:
            raise ValueError("frames must be at least [time, height, width]")
        latest = array[-1]
        return np.repeat(latest[np.newaxis, ...], self.horizon, axis=0)


@dataclass(frozen=True)
class RainfallThresholdRiskScorer:
    """Simple flood-risk score from rainfall accumulations and local thresholds."""

    warning_1h: float
    warning_3h: float
    warning_6h: float

    def score(self, rain_1h: float, rain_3h: float, rain_6h: float) -> float:
        ratios = [
            rain_1h / self.warning_1h if self.warning_1h else 0.0,
            rain_3h / self.warning_3h if self.warning_3h else 0.0,
            rain_6h / self.warning_6h if self.warning_6h else 0.0,
        ]
        return float(max(0.0, min(1.0, max(ratios))))

    def label(self, rain_1h: float, rain_3h: float, rain_6h: float) -> str:
        score = self.score(rain_1h, rain_3h, rain_6h)
        if score >= 1.0:
            return "warning"
        if score >= 0.8:
            return "watch"
        return "normal"
