"""Persist input-only baseline forecasts and score arriving native radar observations."""

from __future__ import annotations

import argparse
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import numpy as np

from minxionghydrocast import __version__
from minxionghydrocast.ingestion import cwa_grid
from minxionghydrocast.io.data_store import (
    DataLayout, atomic_write_bytes, require_external_data_root, sha256_file,
)
from minxionghydrocast.models import baselines, metrics
from minxionghydrocast.models.radar_tensor import valid_value_mask
from minxionghydrocast.models.rolling_backtest import (
    BacktestConfig, BacktestEvent, BacktestManifest, RadarFrame, aware_time,
)
from minxionghydrocast.pipelines import optical_flow_evaluation, tensor_baseline_evaluation
from minxionghydrocast.pipelines.backtest_store import (
    backtest_lock, digest, load_record, save_record,
)

JSON_SUFFIX = ".json"
FrameData = tuple[dict[str, Any], np.ndarray]
FrameReader = Callable[[RadarFrame], FrameData]


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
    grid = {name: getattr(inspection, name) for name in (
        "data_id", "units", "crs", "start_longitude", "start_latitude", "grid_resolution",
        "grid_dimension_x", "grid_dimension_y", "nodata_values",
    )}
    grid["nodata_values"] = list(grid["nodata_values"])
    return grid


def _frame_reader(layout: DataLayout, config: BacktestConfig) -> FrameReader:
    @lru_cache(maxsize=config.input_length + config.horizon + 2)
    def cached(path_name: str, time: str, byte_count: int, checksum: str) -> FrameData:
        path = layout.resolve_relative(path_name)
        if not path.is_file():
            raise FileNotFoundError(path_name)
        if path.stat().st_size != byte_count or sha256_file(path) != checksum:
            raise ValueError(f"source frame integrity failure: {path_name}")
        inspection, values = cwa_grid.extract_cwa_grid_values(path)
        if aware_time(inspection.data_time) != aware_time(time):
            raise ValueError("frame header timestamp differs from manifest timestamp")
        grid = _grid(inspection)
        return grid, np.asarray(values, dtype=np.float32).reshape(
            inspection.grid_dimension_y, inspection.grid_dimension_x, 1
        )

    def read(reference: RadarFrame) -> FrameData:
        return cached(reference.path, reference.data_time, reference.bytes, reference.sha256)
    return read


@dataclass(frozen=True)
class _Forecast:
    path: Path
    predictions: np.ndarray
    latest_mask: np.ndarray
    record: dict[str, Any]


def _read_forecast(path: Path, expected: dict[str, Any]) -> _Forecast:
    record = load_record(path.with_suffix(JSON_SUFFIX))
    if record.get("context") != expected:
        raise ValueError("forecast input identity changed for existing origin/configuration")
    try:
        if sha256_file(path) != record["array_sha256"]:
            raise ValueError("checksum mismatch")
        with np.load(path, allow_pickle=False) as archive:
            predictions = archive["predictions"]
            mask = archive["last_input_valid"]
        grid = record["grid"]
        shape = (len(expected["config"]["models"]), expected["config"]["horizon"],
                 grid["grid_dimension_y"], grid["grid_dimension_x"], 1)
        if predictions.shape != shape or mask.shape != shape[2:]:
            raise ValueError("shape mismatch")
        return _Forecast(path, predictions, mask.astype(bool), record)
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError("forecast array integrity failure") from exc


def _safe_manifest_path(layout: DataLayout, requested: Path) -> Path:
    requested = requested.expanduser()
    if requested.is_absolute():
        try:
            requested = requested.resolve().relative_to(layout.root)
        except ValueError as exc:
            raise ValueError("manifest must remain inside the configured data root") from exc
    return layout.resolve_relative(requested.as_posix())


class _Runner:
    """One immutable manifest snapshot and bounded generation/scoring pass."""

    def __init__(self, layout: DataLayout, config: BacktestConfig, cutoff: datetime,
                 max_new_windows: int, manifest: BacktestManifest, raw_manifest: bytes):
        self.layout, self.config, self.cutoff = layout, config, cutoff
        self.max_new_windows = max_new_windows
        self.manifest, self.raw_manifest = manifest, raw_manifest
        self.config_payload = config.model_dump(mode="json")
        self.identity = {"config": self.config_payload, "code": code_identity(),
                         "numpy": np.__version__, "package_version": __version__}
        self.configuration_id = digest(self.identity)
        self.store = layout.resolve_relative("backtests")
        for name in (".lock", "runs", "manifests", "latest.json"):
            layout.resolve_relative(f"backtests/{name}")
        self.counts: dict[str, int] = dict.fromkeys(("new_forecasts", "cached_forecasts", "new_scores",
                                    "cached_scores", "deferred_origins"), 0)
        self.windows: list[dict[str, Any]] = []
        self.excluded: list[dict[str, str]] = []
        self.step = timedelta(minutes=config.cadence_minutes)
        self.read_frame = _frame_reader(layout, config)

    def forecast_path(self, event_id: str, origin: datetime) -> Path:
        directory = f"backtests/{self.configuration_id}/{event_id}/{origin:%Y%m%dT%H%M%S%fZ}"
        self.layout.resolve_relative(f"{directory}/forecast.json")
        return self.layout.resolve_relative(f"{directory}/forecast.npz")

    def predict(self, inputs: np.ndarray, nodata: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
        input_mask = valid_value_mask(inputs, nodata)
        outputs = []
        for model in self.config.models:
            if model == "persistence":
                output = tensor_baseline_evaluation.persistence_predict(inputs, horizon=self.config.horizon)
            else:
                output = optical_flow_evaluation.optical_flow_predict(
                    inputs, horizon=self.config.horizon, input_mask=input_mask,
                    max_displacement=self.config.max_displacement,
                    min_valid_pixels=self.config.min_valid_pixels,
                    fill_value=nodata[0] if nodata else float("nan"),
                )
            outputs.append(output)
        return np.stack(outputs), input_mask[-1]

    def forecast(self, event_id: str, origin: datetime, refs: list[RadarFrame], path: Path) -> _Forecast:
        context = {"event_id": event_id, "issue_time": origin.isoformat(),
                   "configuration_id": self.configuration_id, "config": self.config_payload,
                   "inputs": [f.model_dump(mode="json") for f in refs]}
        committed = path.with_suffix(JSON_SUFFIX).exists()
        # Check identity before reading changed input artifacts.
        cached = _read_forecast(path, context) if committed else None
        inputs = [self.read_frame(f) for f in refs]
        grid = inputs[0][0]
        if any(g != grid for g, _ in inputs):
            raise ValueError("input grid contract changed")
        if cached is not None:
            if cached.record["grid"] != grid:
                raise ValueError("cached forecast grid contract changed")
            self.counts["cached_forecasts"] += 1
            return cached
        predictions, latest_mask = self.predict(np.stack([a for _, a in inputs]), tuple(grid["nodata_values"]))
        payload = io.BytesIO()
        np.savez_compressed(payload, predictions=predictions, last_input_valid=latest_mask)
        atomic_write_bytes(path, payload.getvalue())
        record = {"context": context, "grid": grid, "identity": self.identity,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "array_sha256": hashlib.sha256(payload.getvalue()).hexdigest(),
                  "mode": "retrospective_replay"}
        save_record(path.with_suffix(JSON_SUFFIX), record)
        self.counts["new_forecasts"] += 1
        return _Forecast(path, predictions, latest_mask, record)

    def lead_metrics(self, forecast: _Forecast, target: np.ndarray, lead: int) -> dict[str, Any]:
        nodata = tuple(forecast.record["grid"]["nodata_values"])
        mask = forecast.latest_mask & valid_value_mask(target, nodata)
        mask &= np.all(valid_value_mask(forecast.predictions[:, lead - 1], nodata), axis=0)
        if not mask.any():
            return {}
        return {model: optical_flow_evaluation.evaluate_masked_arrays_with_mae(
            prediction=forecast.predictions[i, lead - 1], target=target,
            evaluation_mask=mask, event_threshold=self.config.event_threshold,
        ) for i, model in enumerate(self.config.models)}

    def score(self, forecast: _Forecast, target_ref: RadarFrame | None,
              target_time: datetime, lead: int) -> dict[str, Any]:
        result: dict[str, Any] = {
            "lead_time_minutes": self.config.cadence_minutes * lead,
            "target_time": target_time.isoformat(), "status": "pending",
            "reason": "target_after_as_of" if target_time > self.cutoff else "target_not_captured",
        }
        if target_time > self.cutoff or target_ref is None:
            return result
        try:
            grid, target = self.read_frame(target_ref)
        except FileNotFoundError:
            return {**result, "status": "excluded", "reason": "target_file_missing"}
        if grid != forecast.record["grid"]:
            raise ValueError("target grid contract differs from forecast grid")
        relative = forecast.path.parent.relative_to(self.layout.root).as_posix()
        path = self.layout.resolve_relative(f"{relative}/scores/{lead:03d}.json")
        context = {"forecast_sha256": forecast.record["array_sha256"],
                   "target": target_ref.model_dump(mode="json"), "lead": lead}
        if path.exists():
            cached = load_record(path)
            if cached.get("context") != context:
                raise ValueError("cached score target identity changed")
            self.counts["cached_scores"] += 1
            return cached["result"]
        metrics_by_model = self.lead_metrics(forecast, target, lead)
        result.update(status="scored" if metrics_by_model else "excluded",
                      reason="" if metrics_by_model else "no_common_valid_pixels",
                      metrics=metrics_by_model)
        save_record(path, {"context": context, "result": result})
        self.counts["new_scores"] += 1
        return result

    def window(self, event: BacktestEvent, origin: datetime, by_time: dict[datetime, RadarFrame]) -> None:
        issue_time = origin.isoformat()
        expected = [origin - self.step * i for i in range(self.config.input_length - 1, -1, -1)]
        if any(t not in by_time for t in expected):
            self.excluded.append({"event_id": event.event_id, "issue_time": issue_time, "reason": "input_gap"})
            return
        path = self.forecast_path(event.event_id, origin)
        if not path.with_suffix(JSON_SUFFIX).exists() and self.counts["new_forecasts"] >= self.max_new_windows:
            self.counts["deferred_origins"] += 1
            return
        try:
            forecast = self.forecast(event.event_id, origin, [by_time[t] for t in expected], path)
        except FileNotFoundError:
            self.excluded.append({"event_id": event.event_id, "issue_time": issue_time, "reason": "input_file_missing"})
            return
        leads = []
        for lead in range(1, self.config.horizon + 1):
            target_time = origin + self.step * lead
            leads.append(self.score(forecast, by_time.get(target_time), target_time, lead))
        self.windows.append({"event_id": event.event_id, "issue_time": issue_time,
                             "forecast_path": self.layout.relative(path), "grid": forecast.record["grid"],
                             "created_at": forecast.record["created_at"], "leads": leads})

    def snapshot(self) -> None:
        checksum = hashlib.sha256(self.raw_manifest).hexdigest()
        path = self.layout.resolve_relative(f"backtests/manifests/{checksum}.json")
        if path.exists():
            if sha256_file(path) != checksum:
                raise ValueError("manifest snapshot integrity failure")
        else:
            atomic_write_bytes(path, self.raw_manifest)

    def report(self) -> dict[str, Any]:
        for status in ("scored", "pending", "excluded"):
            self.counts[f"{status}_leads"] = sum(
                lead["status"] == status for window in self.windows for lead in window["leads"]
            )
        record = {"schema_version": "1.0", "scope": "label_free_research_backtest",
                  "configuration_id": self.configuration_id, "identity": self.identity,
                  "manifest_sha256": hashlib.sha256(self.raw_manifest).hexdigest(),
                  "as_of": self.cutoff.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
                  "counts": self.counts, "windows": self.windows, "excluded_origins": self.excluded,
                  "overlapping_origins_are_independent_events": False,
                  "forecast_publication_ready": False}
        save_record(self.layout.resolve_relative(f"backtests/runs/{digest(record)}.json"), record)
        save_record(self.layout.resolve_relative("backtests/latest.json"), record)
        return record

    def execute(self) -> dict[str, Any]:
        with backtest_lock(self.store):
            self.snapshot()
            for event in self.manifest.events:
                by_time = {aware_time(f.data_time): f for f in event.frames}
                for origin in by_time:
                    if origin <= self.cutoff:
                        self.window(event, origin, by_time)
            return self.report()


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
    safe_manifest = _safe_manifest_path(layout, manifest_path)
    raw_manifest = safe_manifest.read_bytes()
    manifest = BacktestManifest.model_validate_json(raw_manifest)
    return _Runner(layout, config, cutoff, max_new_windows, manifest, raw_manifest).execute()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Manifest inside --root; relative paths are root-relative.")
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
