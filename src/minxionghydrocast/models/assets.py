"""External model asset manifest helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalAsset:
    name: str
    kind: str
    path: Path
    required: bool = True
    description: str = ""

    def exists(self) -> bool:
        return self.path.exists()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        payload["exists"] = self.exists()
        return payload


@dataclass(frozen=True)
class AssetManifest:
    assets: tuple[ExternalAsset, ...]

    def missing_required(self) -> list[ExternalAsset]:
        return [asset for asset in self.assets if asset.required and not asset.exists()]

    def to_dict(self) -> dict[str, object]:
        return {
            "assets": [asset.to_dict() for asset in self.assets],
            "missing_required": [asset.name for asset in self.missing_required()],
        }


def default_nowcastnet_manifest(
    *,
    code_dir: Path,
    checkpoint: Path | None,
    radar_dataset: Path | None,
) -> AssetManifest:
    assets = [
        ExternalAsset(
            name="nowcastnet_code",
            kind="code",
            path=code_dir / "nowcasting" / "models" / "nowcastnet.py",
            description="External NowcastNet implementation entry file.",
        )
    ]
    if checkpoint is not None:
        assets.append(
            ExternalAsset(
                name="nowcastnet_checkpoint",
                kind="checkpoint",
                path=checkpoint,
                description="Model checkpoint stored outside git.",
            )
        )
    if radar_dataset is not None:
        assets.append(
            ExternalAsset(
                name="taiwan_radar_dataset",
                kind="dataset",
                path=radar_dataset,
                description="Gridded Taiwan radar tensors stored outside git.",
            )
        )
    return AssetManifest(tuple(assets))


def write_manifest(manifest: AssetManifest, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
