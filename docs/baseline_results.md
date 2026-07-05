# Baseline Results

These results are demo-safe smoke-test results from `data/samples/flood_risk_events.csv` and a
small synthetic radar-like nowcasting case. They are not scientific model performance claims.

Run:

```bash
floodcasttw-evaluate-baselines \
  --events data/samples/flood_risk_events.csv \
  --output data/processed/baseline_evaluation.json
```

## Persistence Nowcasting

- Model: `PersistenceNowcaster`
- Horizon: 3 lead steps
- Input shape: `3 x 2 x 2`
- Target shape: `3 x 2 x 2`
- RMSE: `4.041452 mm`
- Event threshold: `10.0 mm`
- CSI: `0.5`
- POD: `0.5`
- FAR: `0.0`

## Threshold Flood Risk

- Model: `RainfallThresholdRiskScorer`
- Demo events: 5
- CSI: `0.333333`
- POD: `0.5`
- FAR: `0.5`
- Hits: 1
- Misses: 1
- False alarms: 1
- Correct negatives: 2

## Interpretation

Persistence is the first nowcasting benchmark because it is simple and often hard to beat at short
lead times. The threshold scorer is intentionally basic; it gives a transparent flood-risk baseline
before adding LightGBM, ConvLSTM, U-Net, or NowcastNet-style models.
