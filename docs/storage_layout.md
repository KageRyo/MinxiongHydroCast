# Storage Layout and Git Policy

MinxiongHydroCast is one product with three separate storage responsibilities. Keep them as
siblings in a workspace or on separately managed volumes; do not put mutable state inside the Git
working tree.

```text
MinxiongHydroCast-workspace/
├── repo/       # Git checkout: code, tests, templates, docs, and safe samples
├── runtime/    # private service state: venv, snapshots, metrics, logs, backups
└── data/       # private data assets: raw captures, evidence, datasets, models, reports
```

The names are logical. The supplied installer accepts a durable runtime path and creates a stable
`~/.local/share/minxiong-hydrocast` link. Set `MINXIONGHYDROCAST_DATA_ROOT` to the data path; when
it is omitted, the installer creates `<durable-root>-data`. The data root must stay outside the Git
checkout. `MINXIONGHYDROCAST_RESEARCH_ROOT` is accepted only as a temporary compatibility fallback
for an existing deployment.

## What belongs in Git

Track source code, tests, deployment templates, public documentation, schemas, region profiles,
small synthetic samples, data manifests, source registers, checksums, and public-safe aggregate
model results. These files must be sufficient to explain a data asset and rerun its supported
pipeline when the required external inputs are available.

Do not track credentials, local environment files, live snapshots, logs, Prometheus state, virtual
environments, runner worktrees, backups, raw official captures, candidate evidence, tensors, model
checkpoints, or unpublished labels. `.gitignore` prevents accidental staging of generated paths in
the checkout, but it is not a backup policy or access control boundary.

## Runtime and data responsibilities

`runtime/operations` stores immutable observation snapshots used by the API, shadow evaluator, and
backup command. The daily backup command archives this operations store only. `data/` stores the
larger, long-lived data and model artifacts used by event discovery, review, dataset construction,
and evaluation. Its catalogs use relative artifact paths and SHA-256 checksums to make relocation
verifiable without placing data in Git.

Before a storage migration, pause writing timers, create and verify an operations backup, verify
the data catalog, record the existing runtime deployment metadata, and retain the old paths until
health checks and catalog verification succeed. After copying or moving the data tree, use the
no-write-first [`mhc data relocate-root`](data_root_relocation.md) command to update catalogs,
collection paths, and checksums rather than editing JSON by hand. See
[single_host_operations.md](single_host_operations.md) and [data_assets.md](data_assets.md).
