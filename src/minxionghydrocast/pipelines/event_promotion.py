"""Validate reviewed event evidence before formal dataset promotion."""

from __future__ import annotations

from pathlib import Path

from minxionghydrocast.io.research_store import (
    ResearchLayout,
    require_external_research_root,
)
from minxionghydrocast.models.dataset_schemas import RadarDatasetManifest
from minxionghydrocast.models.event_evidence_schemas import EventEvidenceCatalog


def validate_candidate_promotion_gate(
    *,
    manifest: RadarDatasetManifest,
    event_evidence_catalog_path: Path | None,
    repository_root: Path,
) -> None:
    """Reject discovered candidates that lack verified human approval."""
    referenced = [
        event for event in manifest.events if event.evidence_candidate_id is not None
    ]
    if not referenced:
        return
    if event_evidence_catalog_path is None:
        raise ValueError(
            "formal manifest references discovered candidates but no event evidence catalog was provided"
        )

    catalog = EventEvidenceCatalog.model_validate_json(
        event_evidence_catalog_path.read_text(encoding="utf-8")
    )
    layout = ResearchLayout(Path(catalog.research_root))
    require_external_research_root(layout, repository_root=repository_root)

    from minxionghydrocast.pipelines.event_discovery import verify_event_evidence_catalog

    verification_errors = verify_event_evidence_catalog(catalog, layout=layout)
    if verification_errors:
        raise ValueError(
            "event evidence catalog failed checksum verification: "
            + "; ".join(verification_errors)
        )

    candidates = {candidate.candidate_id: candidate for candidate in catalog.candidates}
    failures: list[str] = []
    for event in referenced:
        candidate_id = event.evidence_candidate_id
        candidate = candidates.get(candidate_id or "")
        if candidate is None:
            failures.append(f"{event.event_id}: unknown evidence candidate {candidate_id}")
            continue
        if candidate.source_data_id != manifest.dataset.data_id:
            failures.append(f"{event.event_id}: candidate source data ID does not match manifest")
        if not candidate.radar_collection.complete:
            failures.append(f"{event.event_id}: candidate radar window is incomplete")
        if candidate.review_status != "approved" or candidate.review is None:
            failures.append(f"{event.event_id}: candidate lacks an approved human review")
            continue
        if event.event_type != candidate.weather_regime:
            failures.append(
                f"{event.event_id}: event_type must match reviewed regime "
                f"{candidate.weather_regime}"
            )
        if event.start_time != candidate.window_start_time:
            failures.append(f"{event.event_id}: start_time does not match reviewed candidate")
        if event.end_time != candidate.window_end_time:
            failures.append(f"{event.event_id}: end_time does not match reviewed candidate")

    if failures:
        raise ValueError("candidate promotion gate failed: " + "; ".join(failures))
