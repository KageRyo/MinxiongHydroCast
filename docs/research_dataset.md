# Reproducible Radar Dataset

MinxiongHydroCast builds research datasets in a durable root outside Git. The tracked repository
contains the event manifest, schemas, orchestration code, tests, and documented results. Raw CWA
frames, tensor archives, reports, catalogs, and checkpoints remain external artifacts.

## Storage Contract

Set the research root in the ignored local `.env`:

```dotenv
MINXIONGHYDROCAST_RESEARCH_ROOT=/durable/path/minxiong-hydrocast-research
```

The build creates this layout:

```text
research-root/
├── raw/       # downloaded formal and candidate-event frames
├── events/    # event plans and collection manifests
├── tensors/   # per-event and combined split archives
├── models/    # checkpoints and training results
├── reports/   # persistence and Tiny U-Net evaluations
├── catalog/   # formal dataset catalog and checksum verification report
├── discovery/ # incremental cursor, history indexes, frame metrics, and temporary scan cache
└── evidence/  # candidate-aligned QPE, gauge, and warning captures
```

Do not place the root inside the repository. Do not commit `.env`, raw official data, generated
tensors, evaluation artifacts, or model checkpoints.

## Build Command

Load the ignored environment file and run the complete pipeline:

```bash
set -a
source .env
set +a

mhc dataset-build \
  --manifest data/samples/event_split_manifest.json \
  --root "$MINXIONGHYDROCAST_RESEARCH_ROOT" \
  --train-weighted-unet \
  --epochs 20 \
  --hidden-channels 8 \
  --batch-size 2 \
  --event-weight 4 \
  --early-stopping-patience 5 \
  --device cuda \
  --multi-gpu
```

The command fetches the current CWA history index, downloads each event with retry and atomic
partial-file handling, validates cadence and grid consistency, creates 6-input/6-target sliding
windows, evaluates Persistence, trains the weighted Tiny U-Net, evaluates independent validation
and test events, writes the catalog, and verifies every cataloged checksum. Use
`--history-index <path>` to reproduce from a saved index and `--skip-download` to reuse an already
complete external collection. `--insecure-tls` is an explicit host workaround only when the local
CA chain cannot verify the CWA endpoint.

Run `mhc event-discover` every 10 to 30 minutes to preserve new candidate events before the CWA
history window expires. Its separate `EventEvidenceCatalog` is candidate-only and cannot modify the
formal event manifest. See [continuous_event_evidence.md](continuous_event_evidence.md).

## Data Contract

The tracked manifest uses schema version `2.0` and requires exactly these event-based splits:

- at least two real training events;
- at least one independent validation event;
- at least two independent test events, both covering Minxiong;
- no duplicate, unassigned, overlapping-split, or `demo` event IDs.

Persisted JSON is a transport format, not the contract. Pydantic schemas validate the history
index, event plans, collection manifests, Persistence metrics, Tiny U-Net training result,
model-comparison reports, dataset catalog, and verification report before serialization.
Contracts use strict types and reject unknown fields at these boundaries.

## Current Five-Event Build

The current real CWA `O-A0059-001` build contains 221 frames and 166 sliding windows:

| Event | Split | Frames | Windows | Persistence RMSE | Persistence CSI |
| --- | --- | ---: | ---: | ---: | ---: |
| Taiwan candidate, 2026-07-07 morning | train | 49 | 38 | `12.958233` | `0.236446` |
| Taiwan widespread, 2026-07-10 daytime | train | 61 | 50 | `8.704656` | `0.191180` |
| Taiwan widespread, 2026-07-09 evening | validation | 37 | 26 | `9.654280` | `0.188989` |
| Chiayi/Minxiong, 2026-07-03 afternoon | test | 37 | 26 | `10.421478` | `0.315475` |
| Chiayi/Minxiong, 2026-07-11 early morning | test | 37 | 26 | `9.154027` | `0.119412` |

The weighted Tiny U-Net used 88 training windows and a separate 26-window validation archive.
Validation data was not used for training normalization or gradient updates. Training used two
RTX 4090 GPUs, selected epoch 7 with best validation loss `1.433344`, and stopped early after 12
completed epochs.

| Independent event | Split | Persistence RMSE | Tiny U-Net RMSE | Persistence CSI | Tiny U-Net CSI |
| --- | --- | ---: | ---: | ---: | ---: |
| Taiwan widespread, 2026-07-09 evening | validation | `9.654280` | `8.053179` | `0.188989` | `0.205842` |
| Chiayi/Minxiong, 2026-07-03 afternoon | test | `10.421478` | `9.186911` | `0.315475` | `0.294527` |
| Chiayi/Minxiong, 2026-07-11 early morning | test | `9.154027` | `8.218313` | `0.119412` | `0.122282` |

## Reproducibility Evidence

The latest completed build produced:

- 251 verified artifacts totaling 2,410,640,934 bytes;
- a catalog containing source provenance, event time ranges, split membership, per-artifact SHA-256,
  aggregate metrics, and 10-to-60-minute lead-time metrics;
- a verification report with status `ok` and no checksum or size mismatches;
- catalog SHA-256 `4db1c8f112bd8bc45aa6fe05b06ee4407434931d69acb9ffcdd288d2c80a41a5`.

The external evidence files are `catalog/dataset_catalog.json` and
`catalog/dataset_verification.json` under the configured research root.

## Publication Gate

The weighted Tiny U-Net lowers aggregate RMSE on validation and both test events, but it does not
consistently beat Persistence on CSI and every lead time. In particular, CSI regresses on the
2026-07-03 Minxiong test event. The fail-closed catalog therefore records
`forecast_publication_ready=false` with detailed blockers.

This dataset is usable for reproducible model research and regression testing. It is not enough
to publish an operational forecast. The next model iteration must add weather-regime diversity,
official event context, QPE/gauge validation, and local outcome labels, then pass the same
independent-event promotion gate without weakening it.
