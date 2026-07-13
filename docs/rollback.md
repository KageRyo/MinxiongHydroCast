# Rollback and recovery

Rollback is a controlled restoration of a previously verified application revision or operational
snapshot. It is not permission to discard failed-attempt evidence or overwrite the live store
without validation.

## Triggers

- A deployed revision cannot collect or serve previously valid official contracts.
- Readiness or schema semantics regress and could classify invalid data as healthy.
- A migration corrupts pointers, manifests, or checksums.
- Monitoring, backup, or alert delivery enters a restart/failure loop after deployment.

## Preconditions

- Identify the exact known-good Git commit and its successful CI run.
- Create and verify a current backup when the store remains readable.
- Record current service status, deployed revision, and latest snapshot ID.
- Stop scheduled writers before changing code paths or data directories.

## Application rollback

1. Stop the collector and shadow timers.
2. Check out the known-good commit in a clean worktree.
3. Run its test suite and configuration validators.
4. Run the single-host installer against the private environment file.
5. Verify the installed revision, service status, API readiness, Prometheus target, and one live
   collection.
6. Re-enable timers only after the checks pass.

The installer records `installed-revision.txt` and the Python package set in durable configuration.
Do not deploy an uncommitted worktree.

## Data recovery

1. Keep the active store unchanged while selecting a backup.
2. Verify the archive SHA-256 and metadata sidecar.
3. Restore into a new isolated directory.
4. Verify every restored manifest, dataset checksum, schema checksum, and latest snapshot ID.
5. Stop API and collector writers before an approved active-store switch.
6. Preserve the displaced store for investigation until the incident review is complete.

Never point the API at an unverified restore target. A local backup does not protect against loss of
the complete host or volume; maintain an off-host copy before treating recovery as production-ready.

## Model rollback

Experimental model promotion must use an immutable checkpoint, feature contract, evaluation
artifact, and configuration manifest. To roll back a model:

1. Disable experimental forecast publication and retain official observations.
2. Restore the last approved checkpoint and its exact feature/configuration manifest.
3. Re-run independent-event evaluation and compare it with the recorded approval artifact.
4. Verify that the experimental endpoint remains clearly classified and can fail unavailable.
5. Re-enable only with model-reviewer and service-owner approval.

Do not replace a failed model with an unevaluated checkpoint or relax the persistence-comparison,
calibration, local-label, or shadow gates during rollback.

## Post-rollback validation

- Official live contracts pass for CWA rain, WRA warning, and WRA IoW feeds.
- `GET /readyz` represents the restored data honestly.
- Prometheus scrapes the expected localhost target and alert rules load.
- Alertmanager records a firing/resolved drill without exposing secrets.
- Backup creation and isolated restore still pass.
- The shadow report records any collection gap caused by rollback; it is not manually edited away.
