# Rolling radar backtests

User-approved intent: open three labeled English feature issues, assess delivery and implement
the first. Manual annotations do not exist. Extend existing native-grid baseline evaluation into
a repeatable, one-shot research workflow without changing fixed splits or operational gates.

## Contract

`mhc model rolling-backtest --manifest PATH --root EXTERNAL_ROOT [--as-of ISO]`
reads a strict versioned manifest of event IDs and relative radar-frame paths, aware observation
times, byte counts and SHA-256. A manifest can expand as observations arrive. The runner predicts
at each cadence-aligned origin with sufficient contiguous history. Default inputs/horizon are
six10-minute frames. Persistence and deterministic CPU Optical Flow consume only past inputs.
Learned checkpoints, training, live downloading and deployed timers are outside this delivery.

Forecasts are immutable after their checksummed commit record exists. Configuration, code and
input hashes identify each forecast. Subsequent runs reuse its arrays and score newly available
future observations per origin/lead. Changes in input identity for an existing origin/config
fail closed rather than replace a forecast. Configuration/code changes use a separate store.

Validate source product O-A0059-001, dBZ units, declared datum, timestamps, shape/grid and source
integrity. Missing target references are pending, unavailable target files are explicit exclusions,
missing input histories are excluded and corrupt files fail closed. No target is consulted by
prediction. No normalization or training is performed. Exact targets and a common valid-pixel
mask across baselines yield RMSE/MAE and CSI/POD/FAR using existing scorers. Retain all-nodata
exclusions rather than zero error. Origins may overlap within an event; do not pool them as
independent event samples or average RMSE values.

Store forecast arrays, per-target score envelopes and immutable run reports below the external
data root. Reuse atomic writes and a kernel lock; provide bounded new windows per run. Forecast
metadata is the commit point: an orphan array before that point can be regenerated; committed
artifacts must verify before reuse. Scores are immutable checksum envelopes. Summaries count
states without inventing independent pooled performance. Paths and event IDs are constrained;
raw arrays and private reports are not committed. Provide disabled-by-default user timer/service
templates, documentation, synthetic end-to-end tests and one bounded preserved-data run.
