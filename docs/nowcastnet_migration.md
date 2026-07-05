# NowcastNet Migration

FloodCastTW keeps third-party SOTA code, checkpoints, and radar datasets outside git. The repo
contains only the contract and adapter needed to connect those assets once they are reviewed.

## Radar Tensor Contract

Provisional adapter tensor spec:

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

## External Assets

Keep these outside git under ignored folders such as `data/external/`:

- NowcastNet source code
- Taiwan radar tensor dataset
- Model checkpoints

The sample asset manifest lives at `data/samples/external_asset_manifest.json`.

## Smoke Test

Run the adapter smoke test without loading external NowcastNet code:

```bash
floodcasttw-nowcastnet-smoke \
  --code-dir data/external/nowcastnet/code \
  --checkpoint data/external/checkpoints/nowcastnet_tw.pt \
  --radar-dataset data/external/radar/taiwan \
  --output data/processed/nowcastnet_smoke.json \
  --manifest-output data/processed/nowcastnet_assets.json
```

The smoke test validates the tensor contract using `PersistenceNowcaster`. It reports whether the
external NowcastNet code and required assets are present, but does not import third-party code.

## Before Training

- Confirm radar projection, cadence, and native resolution.
- Split train/validation/test by weather event.
- Run persistence baselines on the same tensors.
- Use one RTX 4090 first; use both GPUs only after data loading and checkpointing are repeatable.
- Add license notices before copying any third-party source into this repository.
