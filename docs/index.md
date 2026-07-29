# Documentation

The README is the project overview. This index routes implementation, operations, research, and
governance details without duplicating changing deployment numbers.

## Understand the project

- [Project identity](project_identity.md): canonical name and package identifiers.
- [Project scope](project_scope.md): supported capabilities, non-goals, and geographic boundary.
- [Architecture](architecture.md): components, data paths, gates, and public/private boundaries.
- [Data source register](data_source_register.md): official authority, purpose, acceptance, and
  redistribution review.
- [Data contracts](data_contracts.md): persisted schemas, provenance, and validation behavior.

## Operate the observation service

- [Operational use](operational_use.md): demo/live profiles, API, readiness, features, and
  production gates.
- [Single-host operations](single_host_operations.md): localhost-only systemd installation,
  monitoring, backup, and shadow evaluation.
- [Deployment status](deployment_status.md): dated, public-safe rollout evidence.
- [Incident response](incident_response.md): detection, triage, containment, and evidence.
- [Rollback](rollback.md): application and data rollback procedure.

## Reproduce the research

- [Research dataset](research_dataset.md): durable external layout, build command, split, and
  checksum evidence.
- [Continuous event evidence](continuous_event_evidence.md): discovery, artifact completeness,
  human review, and formal-promotion boundary.
- [Event splits](event_splits.md): event-level leakage controls.
- [Radar data sources](radar_data_sources.md): official radar/QPE candidates and formats.
- [Radar tensor conversion](radar_tensor_conversion.md): grid and tensor contract.
- [Baseline results](baseline_results.md): smoke and formal independent-event metrics.
- [Model card](model_cards/minxiong_chiayi_baseline.md): intended use, evaluation, and limitations.
- [Model strategy](model_strategy.md): baseline-first model progression.

## Plan and govern

- [Tasks](tasks.md): current actionable work and acceptance checks.
- [Roadmap](roadmap.md): long-term milestones.
- [Completion plan](completion_plan.md): product-level exit criteria.
- [Decision authority](decision_authority.md): who may approve operational and research changes.
- [Security policy](../SECURITY.md): vulnerability reporting and sensitive-data boundaries.
- [Changelog](../CHANGELOG.md): released changes.

`tasks.md` is the source of truth for current work; `roadmap.md` owns longer-term direction.
Runtime counts and gate metrics should be generated from run summaries, with only dated public-safe
snapshots recorded in `deployment_status.md`.
