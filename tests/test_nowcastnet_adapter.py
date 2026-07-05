from pathlib import Path

import numpy as np

from floodcasttw.models.assets import default_nowcastnet_manifest
from floodcasttw.models.nowcastnet_adapter import NowcastNetAdapter, NowcastNetConfig
from floodcasttw.models.radar_tensor import RadarTensorSpec, validate_radar_tensor


def test_radar_tensor_spec_shapes_and_validation():
    spec = RadarTensorSpec(input_length=2, prediction_length=3, height=4, width=5, channels=1)

    assert spec.total_length == 5
    assert spec.input_shape == (2, 4, 5, 1)
    assert spec.target_shape == (3, 4, 5, 1)
    validate_radar_tensor(np.zeros(spec.input_shape), spec, kind="input")


def test_radar_tensor_validation_rejects_wrong_shape():
    spec = RadarTensorSpec(input_length=2, prediction_length=3, height=4, width=5, channels=1)

    try:
        validate_radar_tensor(np.zeros((2, 4, 5)), spec, kind="input")
    except ValueError as exc:
        assert "does not match expected" in str(exc)
    else:
        raise AssertionError("expected shape validation to fail")


def test_asset_manifest_reports_missing_required_assets(tmp_path: Path):
    manifest = default_nowcastnet_manifest(
        code_dir=tmp_path / "nowcastnet" / "code",
        checkpoint=tmp_path / "checkpoints" / "model.pt",
        radar_dataset=tmp_path / "radar",
    )

    assert [asset.name for asset in manifest.missing_required()] == [
        "nowcastnet_code",
        "nowcastnet_checkpoint",
        "taiwan_radar_dataset",
    ]


def test_nowcastnet_healthcheck_and_smoke_test(tmp_path: Path):
    config = NowcastNetConfig(
        code_dir=tmp_path / "nowcastnet" / "code",
        input_length=2,
        total_length=5,
        image_height=4,
        image_width=5,
    )
    adapter = NowcastNetAdapter(config)

    healthcheck = adapter.healthcheck()
    smoke = adapter.smoke_test_with_persistence()

    assert healthcheck["available"] is False
    assert healthcheck["tensor_spec"]["input_length"] == 2
    assert smoke["status"] == "ok"
    assert smoke["input_shape"] == [2, 4, 5, 1]
    assert smoke["prediction_shape"] == [3, 4, 5, 1]
