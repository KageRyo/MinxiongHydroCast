"""Radar tensor contract for nowcasting models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class RadarTensorSpec:
    input_length: int = 9
    prediction_length: int = 20
    height: int = 512
    width: int = 512
    channels: int = 1
    cadence_minutes: int = 6
    units: str = "mm_per_hour"
    crs: str = "EPSG:4326"

    @property
    def total_length(self) -> int:
        return self.input_length + self.prediction_length

    @property
    def input_shape(self) -> tuple[int, int, int, int]:
        return (self.input_length, self.height, self.width, self.channels)

    @property
    def target_shape(self) -> tuple[int, int, int, int]:
        return (self.prediction_length, self.height, self.width, self.channels)

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


def validate_radar_tensor(array, spec: RadarTensorSpec, *, kind: str = "input") -> None:
    expected = spec.input_shape if kind == "input" else spec.target_shape
    actual = tuple(np.asarray(array).shape)
    if actual != expected:
        raise ValueError(f"{kind} radar tensor shape {actual} does not match expected {expected}")


def save_spec(spec: RadarTensorSpec, path: Path) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec.to_dict(), indent=2) + "\n", encoding="utf-8")
