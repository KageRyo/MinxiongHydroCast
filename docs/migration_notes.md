# Migration Notes

This repository intentionally keeps only the parts needed for a clean public/private engineering
base.

## Migrated

- Rainfall alert ingestion with explicit `demo` and `live` modes.
- Rain gauge and flood-sensor demo outputs with explicit sample metadata.
- Safer shelter parsing helpers and tests.
- Baseline model code for rainfall nowcasting and threshold flood-risk scoring.
- A NowcastNet adapter boundary for future SOTA migration.
- Environment examples, package metadata, docs, tests, and sample CSV files.

## Not Migrated

- `Readme.md` from the old project because it contained credentials and private service notes.
- Historical notebooks because they mix exploration, brittle XPath selectors, and generated output.
- `weather_sota.zip` because third-party source archives and model weights should not be committed
  without a license and reproducibility review.
- Real source exports and generated CSV files that may contain personal contact information.
