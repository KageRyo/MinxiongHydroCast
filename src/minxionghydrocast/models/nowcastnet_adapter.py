"""Adapter boundary for a future NowcastNet migration.

The original project carried a small `weather_sota.zip` research capsule. This repo does not
commit that archive or third-party weights. Instead, keep a narrow adapter boundary so the model
can be wired in once radar tensors, checkpoints, and license notices are available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from minxionghydrocast.models.assets import AssetManifest, default_nowcastnet_manifest
from minxionghydrocast.models.baselines import PersistenceNowcaster
from minxionghydrocast.models.radar_tensor import RadarTensorSpec, validate_radar_tensor


@dataclass
class NowcastNetConfig:
    code_dir: Path
    checkpoint: Path | None = None
    radar_dataset: Path | None = None
    device: str = "cuda"
    input_length: int = 9
    total_length: int = 29
    image_height: int = 512
    image_width: int = 512
    channels: int = 1

    @property
    def prediction_length(self) -> int:
        return self.total_length - self.input_length

    def tensor_spec(self) -> RadarTensorSpec:
        return RadarTensorSpec(
            input_length=self.input_length,
            prediction_length=self.prediction_length,
            height=self.image_height,
            width=self.image_width,
            channels=self.channels,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["code_dir"] = str(self.code_dir)
        payload["checkpoint"] = str(self.checkpoint) if self.checkpoint else ""
        payload["radar_dataset"] = str(self.radar_dataset) if self.radar_dataset else ""
        return payload


class NowcastNetAdapter:
    """Lazy adapter for an external NowcastNet implementation."""

    def __init__(self, config: NowcastNetConfig):
        self.config = config

    def is_available(self) -> bool:
        return (self.config.code_dir / "nowcasting" / "models" / "nowcastnet.py").exists()

    def asset_manifest(self) -> AssetManifest:
        return default_nowcastnet_manifest(
            code_dir=self.config.code_dir,
            checkpoint=self.config.checkpoint,
            radar_dataset=self.config.radar_dataset,
        )

    def healthcheck(self) -> dict[str, object]:
        manifest = self.asset_manifest()
        return {
            "available": self.is_available(),
            "config": self.config.to_dict(),
            "tensor_spec": self.config.tensor_spec().to_dict(),
            "assets": manifest.to_dict(),
            "requirements": self.explain_requirements(),
        }

    def smoke_test_with_persistence(self) -> dict[str, object]:
        """Validate the tensor contract without loading external NowcastNet code."""

        spec = self.config.tensor_spec()
        input_tensor = np.zeros(spec.input_shape, dtype=np.float32)
        validate_radar_tensor(input_tensor, spec, kind="input")
        prediction = PersistenceNowcaster(horizon=spec.prediction_length).predict(input_tensor)
        expected_shape = spec.target_shape
        if tuple(prediction.shape) != expected_shape:
            raise ValueError(f"smoke prediction shape {prediction.shape} != {expected_shape}")
        return {
            "status": "ok",
            "adapter_available": self.is_available(),
            "input_shape": list(input_tensor.shape),
            "prediction_shape": list(prediction.shape),
            "tensor_spec": spec.to_dict(),
        }

    def explain_requirements(self) -> str:
        return (
            "NowcastNet needs gridded radar sequences, a compatible PyTorch environment, "
            "GPU memory, and a checkpoint trained or adapted for Taiwan radar data."
        )

    def predict(self, radar_sequence):
        raise NotImplementedError(
            "NowcastNet inference is not wired yet. Use PersistenceNowcaster as the baseline "
            "until radar tensors and checkpoints are prepared."
        )
