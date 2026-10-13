# 文件總覽 / Documentation

The README is the project overview. This index routes implementation, operations, data assets, and
governance details without duplicating changing deployment numbers.

從[快速開始](getting_started.md)體驗合成資料示範，或依任務選擇下方的技術文件。
公開網站不提供即時觀測；[部署狀態](deployment_status.md)中的數字皆為註明日期的歷史證據。

- 操作服務：[API 與狀態判讀](api_reference.md)。
- 開發貢獻：[貢獻入口](contributing.md)與[文件站開發](site_development.md)。

## Understand the project

- [Project identity](project_identity.md): canonical name and package identifiers.
- [Project scope](project_scope.md): supported capabilities, non-goals, and geographic boundary.
- [Architecture](architecture.md): components, data paths, gates, and public/private boundaries.
- [Data source register](data_source_register.md): official authority, purpose, acceptance, and
  redistribution review.
- [Data contracts](data_contracts.md): persisted schemas, provenance, and validation behavior.
- [Storage layout](storage_layout.md): repository, runtime, data-root, and Git boundaries.
- [Data-root relocation](data_root_relocation.md): verified metadata migration after moving data
  assets.

## Operate the observation service

- [Operational use](operational_use.md): demo/live profiles, API, readiness, features, and
  production gates.
- [Single-host operations](single_host_operations.md): localhost-only systemd installation,
  monitoring, backup, and shadow evaluation.
- [Region profiles](region_profiles.md): reusable operational boundaries, coverage, and freshness.
- [Adapter development](adapter_development.md): public source interface and contract tests.
- [Deployment status](deployment_status.md): dated, public-safe rollout evidence.
- [Incident response](incident_response.md): detection, triage, containment, and evidence.
- [Rollback](rollback.md): application and data rollback procedure.

## Build data and model assets

- [Data assets](data_assets.md): durable external layout, build command, split, and
  checksum evidence.
- [v0.2 dataset protocol](v0.2_dataset_protocol.md): tracked manifests, synthetic checks, evidence
  gates, and redistribution boundaries.
- [Continuous event evidence](continuous_event_evidence.md): discovery, artifact completeness,
  human review, and formal-promotion boundary.
- [Event splits](event_splits.md): event-level leakage controls.
- [Radar data sources](radar_data_sources.md): official radar/QPE candidates and formats.
- [Radar tensor conversion](radar_tensor_conversion.md): grid and tensor contract.
- [Baseline results](baseline_results.md): smoke and formal independent-event metrics.
- [Optical-flow baseline](optical_flow_baseline.md): deterministic motion baseline, evaluation,
  and public-safe comparison report.
- [Model card](model_cards/minxiong_chiayi_baseline.md): intended use, evaluation, and limitations.
- [Model strategy](model_strategy.md): baseline-first model progression.

## Plan and govern

- [Tasks](tasks.md): current actionable work and acceptance checks.
- [Roadmap](roadmap.md): long-term milestones.
- [Completion plan](completion_plan.md): product-level exit criteria.
- [Decision authority](decision_authority.md): who may approve operational and data-model changes.
- [Security policy](https://github.com/KageRyo/MinxiongHydroCast/blob/main/SECURITY.md): vulnerability reporting and sensitive-data boundaries.
- [Changelog](https://github.com/KageRyo/MinxiongHydroCast/blob/main/CHANGELOG.md): released changes.

## Additional references

- [Radar source selection](radar_data_sources.md), [source adapters](radar_source_adapters.md),
  [event windows](radar_event_windows.md), and [spatial alignment](spatial_alignment.md).
- [WRA freshness evidence](wra_freshness_evidence.md) and [NowcastNet migration](nowcastnet_migration.md).
- [Release notes](releases/v0.1.6.md) and [migration notes](migration_notes.md).

`tasks.md` is the source of truth for current work; `roadmap.md` owns longer-term direction.
Runtime counts and gate metrics should be generated from run summaries, with only dated public-safe
snapshots recorded in `deployment_status.md`.
