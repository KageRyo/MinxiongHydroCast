"""Persist input-only baseline forecasts and score arriving native radar observations."""

from __future__ import annotations

import argparse
import hashlib
import io
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from minxionghydrocast import __version__
from minxionghydrocast.ingestion import cwa_grid
from minxionghydrocast.io.data_store import (
    DataLayout, atomic_write_bytes, require_external_data_root, sha256_file,
)
from minxionghydrocast.models import baselines, metrics
from minxionghydrocast.models.radar_tensor import valid_value_mask
from minxionghydrocast.models.rolling_backtest import (
    BacktestConfig, BacktestManifest, RadarFrame, aware_time,
)
from minxionghydrocast.pipelines import optical_flow_evaluation, tensor_baseline_evaluation
from minxionghydrocast.pipelines.backtest_store import (
    backtest_lock, digest, load_record, save_record,
)


def code_identity() -> dict[str, str]:
    modules = [baselines, metrics, cwa_grid, optical_flow_evaluation, tensor_baseline_evaluation]
    paths = [Path(__file__), Path(__file__).with_name("backtest_store.py"),
             Path(__file__).parents[1] / "models/rolling_backtest.py",
             Path(__file__).parents[1] / "models/radar_tensor.py"]
    for module in modules:
        if module.__file__ is None:
            raise ValueError("backtest code provenance requires module source files")
        paths.append(Path(module.__file__))
    package = Path(__file__).parents[1]
    return {p.relative_to(package).as_posix(): sha256_file(p) for p in paths}


def _grid(inspection: cwa_grid.CwaGridInspection) -> dict[str, Any]:
    if (not inspection.valid or inspection.data_id != "O-A0059-001"
            or inspection.units != "dBZ" or inspection.crs in ("", "needs_review")
            or inspection.grid_dimension_x < 1 or inspection.grid_dimension_y < 1
            or not np.isfinite([inspection.grid_resolution, inspection.start_latitude,
                                inspection.start_longitude]).all()
            or inspection.grid_resolution <= 0):
        raise ValueError("unsupported radar product, units or grid contract")
    return {name: getattr(inspection, name) for name in (
        "data_id", "units", "crs", "start_longitude", "start_latitude", "grid_resolution",
        "grid_dimension_x", "grid_dimension_y", "nodata_values",
    )}


def _read_forecast(path: Path, expected: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict]:
    record = load_record(path.with_suffix(".json"))
    if record.get("context") != expected:
        raise ValueError("forecast input identity changed for existing origin/configuration")
    try:
        if sha256_file(path) != record["array_sha256"]:
            raise ValueError("checksum mismatch")
        with np.load(path, allow_pickle=False) as archive:
            predictions = archive["predictions"]
            mask = archive["last_input_valid"]
        grid = record["grid"]
        expected_shape = (len(expected["config"]["models"]), expected["config"]["horizon"],
                          grid["grid_dimension_y"], grid["grid_dimension_x"], 1)
        if predictions.shape != expected_shape or mask.shape != expected_shape[2:]:
            raise ValueError("shape mismatch")
        return predictions, mask.astype(bool), record
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError("forecast array integrity failure") from exc


def run_backtest(
    *, manifest_path: Path, root: Path, config: BacktestConfig,
    as_of: datetime | None = None, max_new_windows: int = 24,
) -> dict[str, Any]:
    """Run once; an expanded manifest may score pending leads on later invocations."""
    if max_new_windows < 0:
        raise ValueError("max_new_windows must be nonnegative")
    config = BacktestConfig.model_validate(config.model_dump())
    cutoff = aware_time(as_of or datetime.now(timezone.utc))
    layout = DataLayout(root)
    require_external_data_root(layout, repository_root=Path(__file__).resolve().parents[3])
    raw_manifest = manifest_path.read_bytes()
    manifest = BacktestManifest.model_validate_json(raw_manifest)
    config_payload = config.model_dump(mode="json")
    identity = {"config": config_payload, "code": code_identity(), "numpy": np.__version__,
                "package_version": __version__}
    configuration_id = digest(identity)
    store = layout.resolve_relative("backtests")
    for name in (".lock", "runs", "manifests", "latest.json"):
        layout.resolve_relative(f"backtests/{name}")
    counts = {name: 0 for name in ("new_forecasts", "cached_forecasts", "new_scores",
                                   "cached_scores", "deferred_origins")}
    windows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    step = timedelta(minutes=config.cadence_minutes)

    @lru_cache(maxsize=config.input_length + config.horizon + 2)
    def cached_frame(path_name: str, time: str, byte_count: int, checksum: str) -> tuple[dict[str, Any], np.ndarray]:
        reference = RadarFrame(path=path_name, data_time=time, bytes=byte_count, sha256=checksum)
        path = layout.resolve_relative(reference.path)
        if not path.is_file():
            raise FileNotFoundError(reference.path)
        if path.stat().st_size != reference.bytes or sha256_file(path) != reference.sha256:
            raise ValueError(f"source frame integrity failure: {reference.path}")
        inspection, values = cwa_grid.extract_cwa_grid_values(path)
        if aware_time(inspection.data_time) != aware_time(reference.data_time):
            raise ValueError("frame header timestamp differs from manifest timestamp")
        grid = _grid(inspection)
        # Use JSON-compatible lists in both new and cached records.
        grid["nodata_values"] = list(grid["nodata_values"])
        array = np.asarray(values, dtype=np.float32).reshape(
            inspection.grid_dimension_y, inspection.grid_dimension_x, 1
        )
        return grid, array

    def read_frame(reference: RadarFrame) -> tuple[dict[str, Any], np.ndarray]:
        return cached_frame(reference.path, reference.data_time, reference.bytes, reference.sha256)

    with backtest_lock(store):
        manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
        snapshot = layout.resolve_relative(f"backtests/manifests/{manifest_sha}.json")
        if snapshot.exists():
            if sha256_file(snapshot) != manifest_sha:
                raise ValueError("manifest snapshot integrity failure")
        else:
            atomic_write_bytes(snapshot, raw_manifest)
        for event in manifest.events:
            by_time = {aware_time(f.data_time): f for f in event.frames}
            for origin, reference in by_time.items():
                if origin > cutoff:
                    continue
                issue_time = origin.isoformat()
                expected_times = [origin - step * i for i in range(config.input_length - 1, -1, -1)]
                if any(t not in by_time for t in expected_times):
                    excluded.append({"event_id": event.event_id, "issue_time": issue_time,
                                     "reason": "input_gap"})
                    continue
                refs = [by_time[t] for t in expected_times]
                directory_name = f"backtests/{configuration_id}/{event.event_id}/{origin:%Y%m%dT%H%M%S%fZ}"
                forecast_path = layout.resolve_relative(f"{directory_name}/forecast.npz")
                layout.resolve_relative(f"{directory_name}/forecast.json")
                committed = forecast_path.with_suffix(".json").exists()
                if not committed and counts["new_forecasts"] >= max_new_windows:
                    counts["deferred_origins"] += 1
                    continue
                context = {"event_id": event.event_id, "issue_time": issue_time,
                           "configuration_id": configuration_id, "config": config_payload,
                           "inputs": [f.model_dump(mode="json") for f in refs]}
                if committed:
                    # Check identity before reading changed input artifacts.
                    predictions, latest_mask, saved = _read_forecast(forecast_path, context)
                try:
                    inputs = [read_frame(f) for f in refs]
                except FileNotFoundError:
                    excluded.append({"event_id": event.event_id, "issue_time": issue_time,
                                     "reason": "input_file_missing"})
                    continue
                grid = inputs[0][0]
                if any(g != grid for g, _ in inputs):
                    raise ValueError("input grid contract changed")
                nodata = tuple(grid["nodata_values"])
                if committed:
                    if saved["grid"] != grid:
                        raise ValueError("cached forecast grid contract changed")
                    counts["cached_forecasts"] += 1
                else:
                    input_array = np.stack([a for _, a in inputs])
                    input_mask = valid_value_mask(input_array, nodata)
                    outputs = []
                    for model in config.models:
                        if model == "persistence":
                            output = tensor_baseline_evaluation.persistence_predict(
                                input_array, horizon=config.horizon
                            )
                        else:
                            output = optical_flow_evaluation.optical_flow_predict(
                                input_array, horizon=config.horizon, input_mask=input_mask,
                                max_displacement=config.max_displacement,
                                min_valid_pixels=config.min_valid_pixels,
                                fill_value=nodata[0] if nodata else float("nan"),
                            )
                        outputs.append(output)
                    predictions = np.stack(outputs)
                    latest_mask = input_mask[-1]
                    payload = io.BytesIO()
                    np.savez_compressed(payload, predictions=predictions, last_input_valid=latest_mask)
                    atomic_write_bytes(forecast_path, payload.getvalue())
                    saved = {"context": context, "grid": grid, "identity": identity,
                             "created_at": datetime.now(timezone.utc).isoformat(),
                             "array_sha256": hashlib.sha256(payload.getvalue()).hexdigest(),
                             "mode": "retrospective_replay"}
                    save_record(forecast_path.with_suffix(".json"), saved)
                    counts["new_forecasts"] += 1
                leads = []
                for lead in range(1, config.horizon + 1):
                    target_time = origin + step * lead
                    result: dict[str, Any] = {
                        "lead_time_minutes": config.cadence_minutes * lead,
                        "target_time": target_time.isoformat(), "status": "pending",
                        "reason": "target_after_as_of" if target_time > cutoff else "target_not_captured",
                    }
                    target_ref = by_time.get(target_time)
                    if target_time <= cutoff and target_ref is not None:
                        try:
                            target_grid, target = read_frame(target_ref)
                        except FileNotFoundError:
                            result.update(status="excluded", reason="target_file_missing")
                            leads.append(result)
                            continue
                        if target_grid != grid:
                            raise ValueError("target grid contract differs from forecast grid")
                        score_path = layout.resolve_relative(f"{directory_name}/scores/{lead:03d}.json")
                        score_context = {"forecast_sha256": saved["array_sha256"],
                                         "target": target_ref.model_dump(mode="json"), "lead": lead}
                        if score_path.exists():
                            cached = load_record(score_path)
                            if cached.get("context") != score_context:
                                raise ValueError("cached score target identity changed")
                            result = cached["result"]
                            counts["cached_scores"] += 1
                        else:
                            mask = latest_mask & valid_value_mask(target, nodata)
                            mask &= np.all(valid_value_mask(predictions[:, lead - 1], nodata), axis=0)
                            metrics_by_model = {}
                            if mask.any():
                                for i, model in enumerate(config.models):
                                    metrics_by_model[model] = optical_flow_evaluation.evaluate_masked_arrays_with_mae(
                                        prediction=predictions[i, lead - 1], target=target,
                                        evaluation_mask=mask, event_threshold=config.event_threshold,
                                    )
                            result.update(status="scored" if mask.any() else "excluded",
                                          reason="" if mask.any() else "no_common_valid_pixels",
                                          metrics=metrics_by_model)
                            save_record(score_path, {"context": score_context, "result": result})
                            counts["new_scores"] += 1
                    leads.append(result)
                windows.append({"event_id": event.event_id, "issue_time": issue_time,
                                "forecast_path": layout.relative(forecast_path), "grid": grid,
                                "created_at": saved["created_at"], "leads": leads})
        report = {"schema_version": "1.0", "scope": "label_free_research_backtest",
                  "configuration_id": configuration_id, "identity": identity,
                  "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
                  "as_of": cutoff.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
                  "counts": counts, "windows": windows, "excluded_origins": excluded,
                  "overlapping_origins_are_independent_events": False,
                  "forecast_publication_ready": False}
        for status in ("scored", "pending", "excluded"):
            counts[f"{status}_leads"] = sum(
                lead["status"] == status for window in windows for lead in window["leads"]
            )
        save_record(layout.resolve_relative(f"backtests/runs/{digest(report)}.json"), report)
        save_record(layout.resolve_relative("backtests/latest.json"), report)
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--as-of", type=aware_time)
    parser.add_argument("--input-length", type=int, default=6)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--cadence-minutes", type=int, default=10)
    parser.add_argument("--event-threshold", type=float, default=35.0)
    parser.add_argument("--models", nargs="+", choices=["persistence", "optical_flow"],
                        default=["persistence", "optical_flow"])
    parser.add_argument("--max-new-windows", type=int, default=24)
    parser.add_argument("--max-displacement", type=int, default=8)
    parser.add_argument("--min-valid-pixels", type=int, default=16)
    args = parser.parse_args()
    config = BacktestConfig(**{name: getattr(args, name) for name in (
        "input_length", "horizon", "cadence_minutes", "event_threshold", "models",
        "max_displacement", "min_valid_pixels",
    )})
    report = run_backtest(manifest_path=args.manifest, root=args.root, config=config,
                          as_of=args.as_of, max_new_windows=args.max_new_windows)
    print(f"[OK] rolling backtest: {report['counts']}; report={args.root / 'backtests/latest.json'}")


if __name__ == "__main__":
    main()
