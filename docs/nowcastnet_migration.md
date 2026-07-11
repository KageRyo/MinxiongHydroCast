# NowcastNet Migration

FloodCastMinxiong keeps third-party SOTA code, checkpoints, and radar datasets outside git. The repo
contains only the contract and adapter needed to connect those assets once they are reviewed.

## Radar Tensor Contract

Original NowcastNet-style research code usually expects cropped/resampled radar tensors rather than
the native CWA `921 x 881` grid. Keep the native CWA tensor contract stable first, then add a
separate NowcastNet preprocessing adapter if migration starts.

Legacy provisional adapter tensor spec:

- Input length: 9 frames
- Prediction length: 20 frames
- Shape: `[time, height, width, channels]`
- Height/width: `512 x 512`
- Channels: 1
- Cadence: 6 minutes
- Units: `mm_per_hour`
- CRS: `EPSG:4326`

The sample spec lives at `data/samples/radar_tensor_spec.json`.
Radar source candidates are tracked in `data/samples/radar_source_manifest.json`.
The tiny conversion fixture lives at `data/samples/radar_pixels.csv`.

Current CWA full-event baseline tensors use:

- Source: CWA `O-A0059-001`
- Shape: `[sample, time, height, width, channels]`
- Input length: 6 frames
- Prediction length: 6 frames
- Height/width: `881 x 921`
- Cadence: 10 minutes
- Units: `dBZ`
- CRS: `TWD67`
- Lead times: 10 to 60 minutes

These tensors are sufficient for persistence and Tiny U-Net/RainNet-style diagnostics. They are not
yet enough to justify copying or training third-party NowcastNet code in this repository.

## Readiness Gate

Do not migrate NowcastNet until all of these are true:

- At least several train events and separate validation/test events are collected across typhoon,
  frontal, Mei-yu, and convective regimes.
- Each radar-derived window has official weather context attached; do not infer typhoon or frontal
  labels from radar reflectivity alone.
- QPE/rain-gauge validation reports exist, so radar/QPE is treated as an estimate rather than
  ground truth.
- Persistence and Tiny U-Net/RainNet-style baselines have stable lead-time metrics on the same
  event splits.
- The target NowcastNet implementation, license, dependency stack, checkpoint format, and expected
  tensor shape are reviewed.
- External code, checkpoints, and datasets stay under ignored `data/external/` paths unless a
  license review explicitly permits tracked source integration.

Current status: not ready. The repository now has three complete CWA radar event windows,
full-event lead-time baselines, and per-event QPE/gauge availability tracking. However, event
diversity is still too thin, official weather labels are still pending, and gauge-vs-QPE reports
are blocked until event-time `O-B0045-001` QPE grids are available.

## External Assets

Keep these outside git under ignored folders such as `data/external/`:

- NowcastNet source code
- Taiwan radar tensor dataset
- Model checkpoints

The sample asset manifest lives at `data/samples/external_asset_manifest.json`.

## Smoke Test

Run the adapter smoke test without loading external NowcastNet code:

```bash
floodcast-minxiong-nowcastnet-smoke \
  --code-dir data/external/nowcastnet/code \
  --checkpoint data/external/checkpoints/nowcastnet_tw.pt \
  --radar-dataset data/external/radar/taiwan \
  --output data/processed/nowcastnet_smoke.json \
  --manifest-output data/processed/nowcastnet_assets.json
```

The smoke test validates the tensor contract using `PersistenceNowcaster`. It reports whether the
external NowcastNet code and required assets are present, but does not import third-party code.

Current smoke status:

- Smoke tensor path: passes.
- Adapter availability: false.
- Missing required assets: `nowcastnet_code`, `nowcastnet_checkpoint`,
  `taiwan_radar_dataset`.
- Decision: keep NowcastNet as a SOTA candidate only; do not start migration until the readiness
  gate above is satisfied.

## Before Training

- Confirm radar projection, cadence, and native resolution.
- Split train/validation/test by weather event.
- Run persistence baselines on the same tensors.
- Run Tiny U-Net/RainNet-style diagnostics on the same tensors.
- Use one RTX 4090 first; use both GPUs only after data loading and checkpointing are repeatable.
- Add license notices before copying any third-party source into this repository.
