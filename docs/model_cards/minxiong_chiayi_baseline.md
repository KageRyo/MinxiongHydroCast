# Minxiong/Chiayi Baseline Model Card

## Model Family

- Primary benchmark: `PersistenceNowcaster`
- Learned diagnostic: weighted `TinyUNetNowcaster`
- Task: 10-to-60-minute CWA radar-echo nowcasting
- Grid: Taiwan-wide `881 x 921`, `dBZ`, TWD67, 10-minute cadence
- Local evaluation target: Minxiong Township and Chiayi County
- Publication status: blocked

## Data

The formal dataset contains five real CWA `O-A0059-001` events: two Taiwan-wide training events,
one separate Taiwan-wide validation event, and two held-out Minxiong/Chiayi test events. Each
sample has six input and six target frames. Raw frames, tensor archives, reports, and checkpoints
remain in the configured external research root.

Training uses 88 sliding windows. Validation uses a separate 26-window event archive and does not
contribute to training normalization or gradients. The two local test events contain 26 windows
each and remain independent of training and model selection.

## Training

- Loss: threshold-weighted MSE at `35 dBZ`, event weight `4`
- Hardware: two RTX 4090 GPUs through PyTorch `DataParallel`
- Configured epochs: 20
- Completed epochs: 12
- Best epoch: 7
- Best independent validation loss: `1.433344`
- Early stopping: enabled and triggered

## Independent Evaluation

| Event | Split | Persistence RMSE | Tiny U-Net RMSE | Persistence CSI | Tiny U-Net CSI |
| --- | --- | ---: | ---: | ---: | ---: |
| Taiwan 2026-07-09 | validation | `9.654280` | `8.053179` | `0.188989` | `0.205842` |
| Minxiong/Chiayi 2026-07-03 | test | `10.421478` | `9.186911` | `0.315475` | `0.294527` |
| Minxiong/Chiayi 2026-07-11 | test | `9.154027` | `8.218313` | `0.119412` | `0.122282` |

Tiny U-Net improves aggregate RMSE for all three independent events, but CSI regresses on the
2026-07-03 local test event and some 10-to-60-minute lead-time gates regress. It therefore does
not consistently beat Persistence.

## Intended Use

Use Persistence as the required benchmark and the weighted Tiny U-Net as a research diagnostic
for architecture, loss, and dataset changes. Use the checksummed external catalog to reproduce
comparisons and detect artifact drift.

Do not expose the current neural output through the operational forecast endpoint, use it as an
official warning, or claim calibrated rainfall/flood prediction performance.

## Limitations

- Five events do not cover enough typhoon, frontal, Mei-yu, and convective regimes.
- Radar reflectivity is not surface rainfall or flood depth.
- Official event-time weather context remains incomplete.
- Historical QPE grids are not yet available for gauge validation across every event.
- Reviewed Minxiong flood outcomes and local calibration are still missing.
- The promotion gate remains fail-closed with `forecast_publication_ready=false`.

Dataset construction and complete evidence are documented in
[research_dataset.md](../research_dataset.md).
