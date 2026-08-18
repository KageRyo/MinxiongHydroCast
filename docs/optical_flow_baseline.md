# Optical-flow baseline

MinxiongHydroCast includes a deterministic CPU baseline named
`OpticalFlowNowcaster`. It estimates a global integer translation between each
pair of adjacent input radar frames with FFT phase correlation, takes the
component-wise median motion, and advects the latest frame forward without
wraparound.

This is an explicit-motion benchmark between Persistence and a learned model.
It is not a dense learned optical-flow model and it does not change the
forecast publication gate.

## Contract

- Input: the existing `[time, height, width, channels]` tensor contract, or a
  sliding archive with an independent sample axis.
- Output: the same spatial shape for every target lead time.
- Motion: integer row/column displacement; default search limit is 128 pixels
  per input step.
- Invalid pixels: the archive nodata mask is excluded from motion estimation and
  evaluation uses the same latest-input/target intersection as Persistence.
- Outside-domain pixels: filled with `0.0`; this is configurable for sources
  whose background value differs.
- Metrics: RMSE, MAE, CSI, POD, FAR, valid/ignored pixel counts, and the same
  10-to-60-minute lead-time breakdown used by the other baselines.

The implementation uses NumPy only. It is deterministic and CPU-capable; no
OpenCV, GPU, model weights, or API credentials are required.

## Evaluate one archive

```bash
mhc model evaluate-optical-flow \
  --archive /path/to/event.npz \
  --event-threshold 35 \
  --output /path/to/event_optical_flow.json
```

The result contains both `PersistenceNowcaster` and `OpticalFlowNowcaster`,
including MAE and lead-time metrics. For a CWA radar archive, `35` is in dBZ;
the CLI records the archive units in the output rather than assuming rainfall
millimeters.

## Public-safe aggregate report

After the formal event build has produced per-event optical-flow reports and
the independent Tiny U-Net comparisons, generate a report that contains only
event metadata and aggregate metrics:

```bash
mhc model optical-flow-report \
  --manifest data/samples/event_split_manifest.json \
  --optical-flow-dir "$MINXIONGHYDROCAST_DATA_ROOT/reports" \
  --tiny-unet-dir "$MINXIONGHYDROCAST_DATA_ROOT/reports" \
  --output data/processed/optical_flow_public_report.json
```

The report requires optical-flow results for every formal event and Tiny U-Net
results for the independent validation/test events. It rejects missing events,
event-ID mismatches, split metadata mismatches, inconsistent Persistence
metrics, and inconsistent lead-time grids. It does not copy archive paths,
checkpoint paths, raw source identifiers, or private data metadata into the
public report.

## Reproducibility and limits

The formal event split remains event-based; the report never reassigns an event
or combines frames across train, validation, and test. The report's
`aggregate_by_split.independent` section combines only the validation and held-
out test events.

Global translation is intentionally conservative. It cannot represent rotation,
growth, decay, splitting, merging, or spatially varying storm motion. A lower
RMSE or higher CSI from this baseline does not establish forecast readiness;
the existing independent-event and lead-time promotion gates remain unchanged.
