"""Adapter boundary for a future NowcastNet migration.

The original project carried a small `weather_sota.zip` research capsule. This repo does not
commit that archive or third-party weights. Instead, keep a narrow adapter boundary so the model
can be wired in once radar tensors, checkpoints, and license notices are available.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class NowcastNetConfig:
    code_dir: Path
    checkpoint: Path | None = None
    device: str = "cuda"
    input_length: int = 9
    total_length: int = 29
    image_height: int = 512
    image_width: int = 512


class NowcastNetAdapter:
    """Lazy adapter for an external NowcastNet implementation."""

    def __init__(self, config: NowcastNetConfig):
        self.config = config

    def is_available(self) -> bool:
        return (self.config.code_dir / "nowcasting" / "models" / "nowcastnet.py").exists()

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
