# Data-root relocation

Use `mhc data relocate-root` after the external data tree has been copied or moved to a new
location. The command does not move raw captures, tensors, models, or reports. It updates only
the JSON metadata that binds those files to the root:

- `catalog/dataset_catalog.json` and `discovery/event_evidence_catalog.json` receive the new
  canonical `data_root` value;
- CWA event collection `frames[].output_path` values under the old root are rewritten to the new
  root;
- every affected `ArtifactRecord` is recalculated after its collection manifest changes; and
- a changed dataset catalog receives a fresh `catalog/dataset_verification.json` report.

All catalog artifact paths remain relative to the data root. Collection `output_path` is the only
known absolute path in this contract, which is why it needs an explicit rewrite.

## Procedure

1. Stop data writers, including the event-discovery timer and any dataset build. Keep the old root
   intact until validation succeeds.
2. Copy or move the complete data tree to a new external directory with a tool appropriate for the
   filesystem. Preserve file bytes, names, and permissions. Do not put the new root inside the Git
   checkout.
3. Run the no-write preflight from a clean checkout:

   ```bash
   mhc data relocate-root \
     --old-root /durable/minxiong-hydrocast-data-old \
     --new-root /durable/minxiong-hydrocast-data \
     --repository-root "$PWD"
   ```

4. If the reported document list and counts are expected, repeat it with `--apply`.

   ```bash
   mhc data relocate-root \
     --old-root /durable/minxiong-hydrocast-data-old \
     --new-root /durable/minxiong-hydrocast-data \
     --repository-root "$PWD" \
     --apply
   ```

5. Point `MINXIONGHYDROCAST_DATA_ROOT` at the new root, verify the catalog, run the relevant
   health checks, then re-enable writers. Retain the old root until the deployment and a scheduled
   discovery cycle both succeed.

With `--apply`, every replaced JSON document is preserved below
`<new-root>/migration_backups/data_root_relocation_<timestamp>_<id>/`. The backup manifest states
which files were replaced or created. Writes are atomic per document; if a replacement fails, the
command restores documents already written in that invocation. The command never deletes or
changes data payload files.

## Integrity failures

The preflight rejects missing artifacts, paths escaping the new root, unexpected catalog roots,
and checksum mismatches unrelated to a rewritten collection. Investigate such a mismatch first:
it may indicate an incomplete copy or altered data. Only after that review may an operator use
`--refresh-artifact-checksums` to intentionally record the bytes currently present in the new
root. That option is explicit because it changes integrity evidence beyond relocation metadata.

The command is idempotent. Rerunning it after a successful relocation reports no documents to
write, provided no files changed in the meantime.
