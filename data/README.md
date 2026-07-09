# Data Layout

This repository tracks only synthetic or low-risk sample data. Live captures, source exports,
model-ready datasets, and files containing contact details or credentials must stay out of git.

## Folders

- `raw/`: unmodified source captures from public systems.
- `interim/`: cleaned but not model-ready data.
- `processed/`: validated outputs used by applications or experiments.
- `external/`: locally downloaded third-party datasets, radar grids, or model checkpoints.
- `samples/`: tiny demo CSV files safe for tests and documentation.

Each generated folder is ignored by `.gitignore` except for `.gitkeep`.

Tracked samples include hydrology rows, location references, and starter WGS84 grid specs.
Radar event manifests, event split manifests, and weather-context manifests are also tracked under
`samples/`. `weather_context_source_review.json` tracks official CWA source-review status and
pending historical chart probes. `qpe_gauge_validation_status.json` tracks aggregate availability
and blocked-report states only; raw CWA/WRA captures, QPE/gauge validation reports, tensor
archives, and checkpoints stay in ignored generated folders.
