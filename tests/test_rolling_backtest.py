import fcntl
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from minxionghydrocast.models.rolling_backtest import BacktestConfig, BacktestManifest
from minxionghydrocast.pipelines.rolling_backtest import run_backtest

START = datetime(2026, 7, 1, tzinfo=timezone.utc)


def frame(root: Path, index: int, values=None, **changes) -> dict:
    time = (START + timedelta(minutes=10 * index)).isoformat()
    params = {"DateTime": time, "GridDimensionX": 2, "GridDimensionY": 2,
              "StartPointLongitude": 120.0, "StartPointLatitude": 23.0,
              "GridResolution": 0.01, "Reflectivity": "dBZ", **changes}
    content = values if values is not None else [index * 10.0] * 4
    raw = json.dumps({"cwaopendata": {"dataid": "O-A0059-001", "sent": time,
        "dataset": {"datasetInfo": {"datasetDescription": "radar", "parameterSet": params},
        "contents": {"contentDescription": "資料無效值為-999。使用之座標系統為TWD67。",
                     "content": ",".join(map(str, content))}}}}).encode()
    path = root / f"frames/{index}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": f"frames/{index}.json", "data_time": time,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def manifest(tmp_path: Path, frames: list[dict], event_id="event_one") -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": "1.0", "events": [
        {"event_id": event_id, "frames": frames}]}))
    return path


def config(**changes) -> BacktestConfig:
    return BacktestConfig(input_length=2, horizon=2, models=["persistence", "optical_flow"],
                          min_valid_pixels=1, **changes)


def run(path, root, **kwargs):
    return run_backtest(manifest_path=path, root=root, config=config(), **kwargs)


def test_pending_targets_arrive_without_changing_saved_predictions(tmp_path):
    root = tmp_path / "external"
    frames = [frame(root, i) for i in range(4)]
    path = manifest(tmp_path, frames[:2])
    first = run(path, root, max_new_windows=1)
    assert first["counts"]["new_forecasts"] == 1
    assert first["windows"][0]["leads"][0]["status"] == "pending"
    artifact = root / first["windows"][0]["forecast_path"]
    saved_bytes = artifact.read_bytes()
    manifest(tmp_path, frames)
    second = run(path, root, max_new_windows=0)
    assert second["counts"]["new_forecasts"] == 0
    assert second["counts"]["new_scores"] == 2
    assert artifact.read_bytes() == saved_bytes
    leads = second["windows"][0]["leads"]
    assert [x["lead_time_minutes"] for x in leads] == [10, 20]
    assert leads[0]["metrics"]["persistence"]["rmse"] == 10
    assert leads[1]["metrics"]["persistence"]["rmse"] == 20
    assert leads[0]["metrics"]["persistence"]["valid_pixel_count"] == 4
    assert second["forecast_publication_ready"] is False
    third = run(path, root, max_new_windows=0)
    assert third["counts"]["new_scores"] == 0
    assert third["counts"]["cached_scores"] == 2
    assert third["windows"] == second["windows"]


def test_as_of_never_uses_future_inputs_or_targets(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(4)])
    result = run(path, root, as_of=START + timedelta(minutes=10))
    assert len(result["windows"]) == 1
    assert all(x["status"] == "pending" for x in result["windows"][0]["leads"])
    result = run(path, root, as_of=START + timedelta(minutes=30), max_new_windows=0)
    assert result["counts"]["new_scores"] == 2


def test_future_observation_values_do_not_change_predictions(tmp_path):
    forecast_values = []
    for value in (0, 90):
        root = tmp_path / str(value)
        refs = [frame(root, 0), frame(root, 1), frame(root, 2, [value] * 4)]
        result = run(manifest(tmp_path, refs), root, max_new_windows=1)
        with np.load(root / result["windows"][0]["forecast_path"], allow_pickle=False) as a:
            forecast_values.append(a["predictions"].copy())
    np.testing.assert_array_equal(*forecast_values)


def test_common_mask_ignores_nodata_for_both_models(tmp_path):
    root = tmp_path / "external"
    refs = [frame(root, 0), frame(root, 1, [10, -999, 10, 10]),
            frame(root, 2, [20, 20, -999, 20])]
    result = run(manifest(tmp_path, refs), root, max_new_windows=1)
    metrics = result["windows"][0]["leads"][0]["metrics"]
    assert metrics["persistence"]["valid_pixel_count"] == 2
    assert metrics["optical_flow"]["valid_pixel_count"] == 2
    assert metrics["persistence"]["rmse"] == 10


def test_all_nodata_is_excluded_not_perfect_score(tmp_path):
    root = tmp_path / "external"
    refs = [frame(root, 0), frame(root, 1), frame(root, 2, [-999] * 4)]
    result = run(manifest(tmp_path, refs), root, max_new_windows=1)
    lead = result["windows"][0]["leads"][0]
    assert lead["status"] == "excluded"
    assert lead["reason"] == "no_common_valid_pixels"
    assert lead["metrics"] == {}


@pytest.mark.parametrize("failure", ["source", "forecast", "score"])
def test_tampered_source_or_cached_artifact_fails_closed(tmp_path, failure):
    root = tmp_path / "external"
    refs = [frame(root, i) for i in range(3)]
    path = manifest(tmp_path, refs)
    report = run(path, root, max_new_windows=1)
    if failure == "source":
        p = root / refs[2]["path"]
    elif failure == "forecast":
        p = root / report["windows"][0]["forecast_path"]
    else:
        p = next((root / "backtests").glob("**/scores/*.json"))
    raw = p.read_bytes()
    p.write_bytes(b"x" + raw[1:])
    with pytest.raises(ValueError, match="integrity"):
        run(path, root, max_new_windows=0)


def test_changed_input_identity_cannot_replace_forecast(tmp_path):
    root = tmp_path / "external"
    refs = [frame(root, i) for i in range(3)]
    path = manifest(tmp_path, refs)
    run(path, root, max_new_windows=1)
    refs[1] = frame(root, 1, [42] * 4)
    manifest(tmp_path, refs)
    with pytest.raises(ValueError, match="input identity"):
        run(path, root, max_new_windows=0)


def test_changed_configuration_uses_separate_store(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(3)])
    a = run(path, root, max_new_windows=1)
    b = run_backtest(manifest_path=path, root=root, config=config(event_threshold=20.0),
                     max_new_windows=1)
    assert a["configuration_id"] != b["configuration_id"]
    assert a["windows"][0]["forecast_path"] != b["windows"][0]["forecast_path"]


def test_bounded_new_work_resumes_at_next_origin(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(5)])
    a = run(path, root, max_new_windows=1)
    b = run(path, root, max_new_windows=1)
    assert a["counts"]["new_forecasts"] == b["counts"]["new_forecasts"] == 1
    assert len(b["windows"]) == 2
    assert a["windows"][0] == b["windows"][0]


def test_missing_input_sequence_is_explicit_and_missing_target_can_recover(tmp_path):
    root = tmp_path / "external"
    refs = [frame(root, i) for i in (0, 1, 3)]
    report = run(manifest(tmp_path, refs), root)
    assert any(x["reason"] == "input_gap" for x in report["excluded_origins"])
    assert report["windows"][0]["leads"][0]["reason"] == "target_not_captured"
    refs.insert(2, frame(root, 2))
    later = run(manifest(tmp_path, refs), root, max_new_windows=0)
    assert later["windows"][0]["leads"][0]["status"] == "scored"


@pytest.mark.parametrize("change", [{"Reflectivity": "mm"}, {"GridResolution": .02},
                                    {"DateTime": "2020-01-01T00:00:00+00:00"}])
def test_incompatible_target_contract_fails_closed(tmp_path, change):
    root = tmp_path / "external"
    refs = [frame(root, 0), frame(root, 1), frame(root, 2, **change)]
    with pytest.raises(ValueError, match="grid|timestamp|product"):
        run(manifest(tmp_path, refs), root, max_new_windows=1)


@pytest.mark.parametrize("failure", ["naive_time", "duplicate_time", "duplicate_event",
                                    "path_escape", "absolute_path", "unknown_field"])
def test_manifest_rejects_unsafe_or_ambiguous_contracts(tmp_path, failure):
    refs = [frame(tmp_path, i) for i in range(2)]
    data = json.loads(manifest(tmp_path, refs).read_text())
    if failure == "naive_time":
        data["events"][0]["frames"][0]["data_time"] = "2026-07-01T00:00:00"
    elif failure == "duplicate_time":
        data["events"][0]["frames"].append(refs[0])
    elif failure == "duplicate_event":
        data["events"].append(data["events"][0])
    elif failure in ("path_escape", "absolute_path"):
        data["events"][0]["frames"][0]["path"] = "../secret" if failure == "path_escape" else "/secret"
    else:
        data["unreviewed"] = True
    with pytest.raises(ValueError):
        BacktestManifest.model_validate(data)


def test_concurrent_run_is_rejected(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(2)])
    directory = root / "backtests"
    directory.mkdir()
    with (directory / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="already running"):
            run(path, root)


def test_orphan_uncommitted_forecast_can_be_rebuilt(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(2)])
    result = run(path, root)
    p = root / result["windows"][0]["forecast_path"]
    p.with_suffix(".json").unlink()
    p.write_bytes(b"interrupted uncommitted file")
    rebuilt = run(path, root)
    assert rebuilt["counts"]["new_forecasts"] == 1
    with np.load(p, allow_pickle=False) as a:
        assert a["predictions"].shape[0] == 2


def test_symlink_source_cannot_escape_data_root(tmp_path):
    root = tmp_path / "external"
    refs = [frame(root, i) for i in range(2)]
    outside = tmp_path / "outside.json"
    source = root / refs[0]["path"]
    source.rename(outside)
    source.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes root"):
        run(manifest(tmp_path, refs), root)


def test_target_file_can_arrive_after_forecast(tmp_path):
    root = tmp_path / "external"
    refs = [frame(root, i) for i in range(3)]
    target = root / refs[2]["path"]
    raw = target.read_bytes()
    target.unlink()
    path = manifest(tmp_path, refs)
    first = run(path, root, max_new_windows=1)
    assert first["windows"][0]["leads"][0]["reason"] == "target_file_missing"
    target.write_bytes(raw)
    later = run(path, root, max_new_windows=0)
    assert later["windows"][0]["leads"][0]["status"] == "scored"


def test_output_store_symlink_cannot_escape_data_root(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(2)])
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "backtests").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes root"):
        run(path, root)


def test_cli_creates_report_through_grouped_command(tmp_path):
    import os
    import subprocess
    import sys
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(3)])
    result = subprocess.run([sys.executable, "-c", "from minxionghydrocast.cli import main; main()", "model",
        "rolling-backtest", "--manifest", str(path), "--root", str(root),
        "--input-length", "2", "--horizon", "2", "--max-new-windows", "1"],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")})
    assert result.returncode == 0, result.stderr
    assert "rolling backtest" in result.stdout
    assert (root / "backtests/latest.json").is_file()


@pytest.mark.parametrize("directory", ["runs", "manifests"])
def test_report_outputs_cannot_follow_parent_symlinks_outside_root(tmp_path, directory):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(2)])
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "backtests").mkdir()
    (root / "backtests" / directory).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes root"):
        run(path, root)
    assert not list(outside.iterdir())


def test_manifest_snapshot_integrity_is_checked_before_resume(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(2)])
    run(path, root)
    snapshot = next((root / "backtests/manifests").glob("*.json"))
    snapshot.write_bytes(b"corrupt snapshot")
    with pytest.raises(ValueError, match="manifest.*integrity"):
        run(path, root)


def test_code_identity_includes_both_contract_and_runner_without_name_collision():
    from minxionghydrocast.pipelines.rolling_backtest import code_identity
    identity = code_identity()
    assert "models/rolling_backtest.py" in identity
    assert "pipelines/rolling_backtest.py" in identity
    assert len(identity) == 9
    runner = Path(__file__).parents[1] / "src/minxionghydrocast/pipelines/rolling_backtest.py"
    assert identity["pipelines/rolling_backtest.py"] == hashlib.sha256(runner.read_bytes()).hexdigest()


def test_default_configuration_scores_every_ten_to_sixty_minute_lead(tmp_path):
    root = tmp_path / "external"
    path = manifest(tmp_path, [frame(root, i) for i in range(12)])
    result = run_backtest(manifest_path=path, root=root, config=BacktestConfig(), max_new_windows=1)
    leads = result["windows"][0]["leads"]
    assert [lead["lead_time_minutes"] for lead in leads] == [10, 20, 30, 40, 50, 60]
    assert all(lead["status"] == "scored" for lead in leads)
    assert leads[-1]["metrics"]["persistence"]["rmse"] == 60
