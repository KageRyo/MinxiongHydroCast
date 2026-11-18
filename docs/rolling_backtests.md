# Rolling radar backtests

`mhc model rolling-backtest` saves input-only Persistence and deterministic CPU Optical Flow
forecasts, then scores them when later observations are available. It runs without manual weather
or flood annotations. This command is available in software v0.1.8 and later
([issue #58](https://github.com/KageRyo/MinxiongHydroCast/issues/58)). Install it with
`python -m pip install --upgrade minxiong-hydrocast` before using the examples.

## Input and storage contract

Use an external data root and a versioned manifest. If `mhc event discover` already populated the
data root, [generate the manifest from its catalog](#export-from-event-discovery). To supply your
own manifest, replace the paths, byte counts and SHA-256 placeholders below with the collector's
recorded values.

The manifest file itself must also remain inside `--root`, including after resolving symlinks.
An absolute manifest path is accepted within that root; a relative manifest path is relative to
the data root, rather than the current working directory.

```json
{
  "schema_version": "1.0",
  "events": [{
    "event_id": "research_event_one",
    "frames": [{
      "path": "raw/radar/research_event_one/frame.json",
      "data_time": "2026-07-27T11:00:00+08:00",
      "bytes": 12345,
      "sha256": "<64 lowercase hexadecimal characters>"
    }]
  }]
}
```

Each event needs sufficient contiguous input frames. Frames must be unique and ordered; event
observation ranges must not overlap. Relative paths, including resolved symlinks, must stay inside
the data root. Capture-time source hashes are preferred. Do not replace recorded hashes to excuse
corruption. Source headers must match the manifest's aware observation times, `O-A0059-001`, dBZ,
and a declared, consistent native grid. The command does not infer a weather mechanism or apply
coordinate transformations.

A producer may atomically replace the manifest with an expanded one as captures arrive. Existing
frame identities stay fixed. The backtest command reads one snapshot, records its SHA-256 and
retains a verified copy; it does not edit ingestion catalogs or download missing source files.
The existing collector's `event_collection` timestamps and `raw_radar_frame` artifact records
in an external dataset catalog provide the required fields. The schema is also directly importable
as `minxionghydrocast.models.rolling_backtest.BacktestManifest` for producer-side validation.

For example, export an already verified external dataset catalog using its recorded hashes:

```python
import json
from pathlib import Path
from minxionghydrocast.io.data_store import DataLayout, atomic_write_bytes, canonical_json_bytes
from minxionghydrocast.models.rolling_backtest import BacktestManifest

layout = DataLayout(Path("/external/hydrocast-data"))
catalog = json.loads((layout.catalog / "dataset_catalog.json").read_text())
events = []
for event in catalog["events"]:
    artifacts = event["artifacts"]
    collection_ref = next(a for a in artifacts if a["kind"] == "event_collection")
    collection = json.loads(layout.resolve_relative(collection_ref["path"]).read_text())
    raw = {a["path"]: a for a in artifacts if a["kind"] == "raw_radar_frame"}
    frames = []
    for frame in collection["frames"]:
        relative = layout.relative(Path(frame["output_path"]))
        artifact = raw[relative]
        frames.append({"path": relative, "data_time": frame["data_time"],
                       "bytes": artifact["bytes"], "sha256": artifact["sha256"]})
    events.append({"event_id": event["event_id"], "frames": frames})
manifest = BacktestManifest.model_validate({"schema_version": "1.0", "events": events})
atomic_write_bytes(layout.root / "backtest_manifest.json",
                   canonical_json_bytes(manifest.model_dump(mode="json")))
```

Verify the dataset catalog and collections through their existing integrity workflow before using
this example. Run it against the original data root or a root relocated with the project tooling.

## Export from event discovery

The `mhc model backtest-manifest` command is available in software v0.1.11 and later.

```bash
mhc model backtest-manifest \
  --root /external/hydrocast-data \
  --since 2026-10-21T00:00:00+08:00 \
  --output backtests/inputs/discovery.json
```

Use `--since` to select candidates by first trigger time. Add an exclusive `--until` to limit a
historical run. When two candidate windows overlap, the earlier window takes precedence. The
command reports how many windows overlapped or lacked captured frames. Open windows with saved
frames are eligible, and weather or flood labels are optional for this research.

The command verifies collection metadata and copies recorded radar checksums into the manifest.
Rolling backtests verify the radar files before using them. Run the export again after new
captures arrive. If a catalog update removes or changes a previously exported frame, the command
reports the conflict and preserves the existing manifest. Use a new output file for a different
event selection. If discovery is replacing collections during the export, the command waits up
to 30 seconds for discovery to finish and retries the read.

## Run and resume

```bash
mhc model rolling-backtest \
  --manifest /external/hydrocast-data/backtest_manifest.json \
  --root /external/hydrocast-data \
  --input-length 6 --horizon 6 --cadence-minutes 10 \
  --event-threshold 35 --max-new-windows 24
```

Defaults produce 10–60-minute radar forecasts. Both baselines receive only the origin's past
input frames. No model is trained or normalized by this command. The forecast is committed before
any target is read. Missing input cadence histories/files are explicit excluded origins; targets
not captured yet remain pending. Listed targets whose files are absent are excluded for that run
and can be scored after arrival. Corrupt files, changed cached identities and incompatible
headers/grids fail the run rather than produce a score.

Run the same command after the producer expands the manifest. Existing forecasts and scores are
verified and reused; they are not regenerated. `--max-new-windows 0` only scores existing origins.
The limit bounds **new forecast origins**, not the total reads/checks of previously saved origins.
A long archive can still require substantial verification time; choose a practical research event
set. Forecast origins within one event may overlap, but observations never cross event boundaries.
Research windows and outputs remain separate from the fixed benchmark and curated-promotion path.

`--as-of 2026-07-27T12:00:00+08:00` restricts inputs and targets to their observation times.
This is retrospective replay: it does not prove when an upstream publisher actually made those
bytes available. Forecast metadata records the historical origin and actual creation time
separately; it never claims a July forecast was generated in July when replayed later.

## Reports and integrity

All outputs stay under `<root>/backtests/`:

- `<configuration-id>/<event>/<origin>/forecast.npz` and `forecast.json`: prediction arrays,
  latest-input valid mask and the checksummed commit record containing code/config/input/grid
  provenance. Models, parameters, package and NumPy versions, and source-code digests isolate
  configurations.
- `.../scores/<lead>.json`: immutable checksum envelopes binding the forecast hash, target
  identity and per-model RMSE/MAE/CSI/POD/FAR. Both models use the same intersection of valid
  input, target and prediction pixels. All-invalid leads are excluded, not assigned zero error.
- `manifests/<sha256>.json`: exact, integrity-checked input snapshots.
- `runs/<digest>.json` and `latest.json`: immutable run records and an atomic latest snapshot.
  JSON records contain `record` and `sha256`; consumers verify the latter against the canonical
  record bytes before trusting it.

Run reports retain per-event, per-origin, per-lead results and scored/pending/excluded counts.
They do not average RMSEs or present overlapping origins as independent event samples. Values
and thresholds remain in dBZ, not millimeters or flood probability.

A nonblocking kernel lock rejects concurrent runs. Files are replaced atomically. The forecast
JSON record is its commit point: an interrupted write before that record may be rebuilt, while
an already committed array must match its checksum. Successfully committed earlier origins
remain available if a later source fails; a failed run does not update `latest.json`.
Checksums prove integrity relative to recorded bytes, not source authenticity. Changes to old
input/target identities require investigation; do not delete valid caches to hide a mismatch.

## Scheduling

The supplied `deploy/systemd-user/minxiong-hydrocast-backtest.service` and `.timer` are opt-in
examples. They are not installed or enabled by this change. Install this source revision into
that runtime and set both variables in its private environment file:

```text
MINXIONGHYDROCAST_DATA_ROOT=/external/hydrocast-data
MINXIONGHYDROCAST_BACKTEST_MANIFEST=/external/hydrocast-data/backtest_manifest.json
```

The timer repeats the one-shot command every 20 minutes with a small delay. The producer must
supply the manifest and observation updates. For the discovery catalog, set
`MINXIONGHYDROCAST_BACKTEST_SINCE` to the timezone-aware first-trigger cutoff in the same
environment file and point `MINXIONGHYDROCAST_BACKTEST_MANIFEST` at
`<root>/backtests/inputs/discovery.json`. Add this service drop-in to refresh the manifest
immediately before each backtest:

```ini
[Service]
ExecStartPre=%h/.local/share/minxiong-hydrocast/venv/bin/mhc model backtest-manifest \
  --root ${MINXIONGHYDROCAST_DATA_ROOT} \
  --since ${MINXIONGHYDROCAST_BACKTEST_SINCE} \
  --output ${MINXIONGHYDROCAST_BACKTEST_MANIFEST}
```

The discovery timer collects the radar frames separately. If the export fails, systemd skips
the backtest for that invocation. Check the export and data-root paths before enabling the timer.

## Verification and boundary

```bash
python -m pytest -q tests/test_rolling_backtest.py tests/test_cli.py
```

Synthetic tests cover arriving targets, replay cutoffs, future-target isolation, shared nodata
masks, resume/bounds, changed input/config identity, corrupted sources/caches, root escapes and
concurrent runs. The feature is research-only. It does not change the formal split, learn
checkpoint parameters, approve human labels or satisfy forecast/flood-risk publication gates.
