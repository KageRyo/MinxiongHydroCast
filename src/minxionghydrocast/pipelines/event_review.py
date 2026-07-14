"""Record auditable human decisions for completed event candidates."""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from minxionghydrocast.config import get_settings
from minxionghydrocast.io.research_store import (
    ResearchLayout,
    artifact_record,
    atomic_write_bytes,
    require_external_research_root,
    sha256_file,
    write_schema_if_changed,
)
from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from minxionghydrocast.models.event_evidence_schemas import (
    EventCandidate,
    EventEvidenceCatalog,
    EventReviewRecord,
    OfficialContextArtifact,
    WeatherRegime,
    aware_datetime,
)
from minxionghydrocast.pipelines.event_discovery import (
    iso_seconds,
    load_event_evidence_catalog,
    now_taipei,
    verify_event_evidence_catalog,
)

PIPELINE_NAME = "event_review"
LOGGER = logging.getLogger(__name__)
DECISIONS = ("approved", "rejected")
WEATHER_REGIMES = ("unclassified", "typhoon", "front", "mei_yu", "convective", "other")


@dataclass(frozen=True)
class EventReviewResult:
    catalog_path: Path
    candidate_id: str
    decision: str
    catalog_changed: bool


@dataclass(frozen=True)
class OfficialContextInput:
    source_url: str
    file_path: Path
    publisher: str
    published_at: str


def _official_context_inputs(
    *,
    references: tuple[str, ...],
    files: tuple[Path, ...],
    publishers: tuple[str, ...],
    published_at: tuple[str, ...],
    fetched_at: datetime,
) -> tuple[OfficialContextInput, ...]:
    counts = {
        len(references),
        len(files),
        len(publishers),
        len(published_at),
    }
    if counts == {0}:
        return ()
    if len(counts) != 1:
        raise ValueError(
            "official context URLs, files, publishers, and published times "
            "must have matching counts"
        )

    inputs = []
    for reference, file_path, publisher, published in zip(
        references,
        files,
        publishers,
        published_at,
        strict=True,
    ):
        if not reference.startswith("https://"):
            raise ValueError("official context references must use HTTPS URLs")
        if publisher != publisher.strip() or not publisher:
            raise ValueError("official context publisher must be trimmed and non-blank")
        published_time = aware_datetime(published, field="official context published_at")
        if fetched_at < published_time:
            raise ValueError("official context fetched_at cannot precede published_at")
        resolved_file = file_path.expanduser().resolve()
        if not resolved_file.is_file() or resolved_file.stat().st_size == 0:
            raise ValueError(f"official context file is missing or empty: {file_path}")
        inputs.append(
            OfficialContextInput(
                source_url=reference,
                file_path=resolved_file,
                publisher=publisher,
                published_at=published,
            )
        )
    return tuple(inputs)


def _safe_context_filename(path: Path) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", path.name).strip("._")
    return (safe_name or "official-context")[:120]


def _persist_official_context(
    *,
    layout: ResearchLayout,
    candidate_id: str,
    inputs: tuple[OfficialContextInput, ...],
    fetched_at: datetime,
) -> tuple[OfficialContextArtifact, ...]:
    contexts = []
    for index, item in enumerate(inputs):
        source_sha256 = sha256_file(item.file_path)
        destination = (
            layout.evidence
            / candidate_id
            / "official_context"
            / (
                f"{index:02d}_{source_sha256[:12]}_"
                f"{_safe_context_filename(item.file_path)}"
            )
        )
        if (
            not destination.is_file()
            or destination.stat().st_size != item.file_path.stat().st_size
            or sha256_file(destination) != source_sha256
        ):
            atomic_write_bytes(destination, item.file_path.read_bytes())
        contexts.append(
            OfficialContextArtifact(
                publisher=item.publisher,
                source_url=item.source_url,
                published_at=item.published_at,
                fetched_at=iso_seconds(fetched_at),
                artifact=artifact_record(
                    layout,
                    destination,
                    kind="official_weather_context",
                ),
            )
        )
    return tuple(contexts)


def _same_official_context(
    review: EventReviewRecord,
    inputs: tuple[OfficialContextInput, ...],
) -> bool:
    if len(review.official_context_artifacts) != len(inputs):
        return False
    return all(
        context.source_url == item.source_url
        and context.publisher == item.publisher
        and context.published_at == item.published_at
        and context.artifact.bytes == item.file_path.stat().st_size
        and context.artifact.sha256 == sha256_file(item.file_path)
        for context, item in zip(
            review.official_context_artifacts,
            inputs,
            strict=True,
        )
    )


def _same_review(
    review: EventReviewRecord,
    *,
    decision: str,
    reviewer: str,
    weather_regime: str,
    official_context_references: tuple[str, ...],
    official_context_inputs: tuple[OfficialContextInput, ...],
    notes: str,
) -> bool:
    return (
        review.decision == decision
        and review.reviewer == reviewer
        and review.weather_regime == weather_regime
        and review.official_context_references == official_context_references
        and _same_official_context(review, official_context_inputs)
        and review.notes == notes
    )


def review_event_candidate(
    *,
    catalog_path: Path,
    repository_root: Path,
    candidate_id: str,
    decision: str,
    reviewer: str,
    weather_regime: WeatherRegime,
    official_context_references: tuple[str, ...] = (),
    official_context_files: tuple[Path, ...] = (),
    official_context_publishers: tuple[str, ...] = (),
    official_context_published_at: tuple[str, ...] = (),
    notes: str = "",
    now: datetime | None = None,
) -> EventReviewResult:
    if decision not in DECISIONS:
        raise ValueError(f"unsupported review decision: {decision}")
    current_time = now or now_taipei()
    context_inputs = _official_context_inputs(
        references=official_context_references,
        files=official_context_files,
        publishers=official_context_publishers,
        published_at=official_context_published_at,
        fetched_at=current_time,
    )
    initial_catalog = load_event_evidence_catalog(catalog_path)
    layout = ResearchLayout(Path(initial_catalog.research_root))
    require_external_research_root(layout, repository_root=repository_root)

    with layout.event_discovery_lock():
        catalog = load_event_evidence_catalog(catalog_path)
        if Path(catalog.research_root).resolve() != layout.root:
            raise ValueError("event evidence catalog research_root changed during review")
        verification_errors = verify_event_evidence_catalog(catalog, layout=layout)
        if verification_errors:
            raise RuntimeError(
                "event evidence catalog verification failed: "
                + "; ".join(verification_errors)
            )

        candidates = list(catalog.candidates)
        candidate_index = next(
            (
                index
                for index, candidate in enumerate(candidates)
                if candidate.candidate_id == candidate_id
            ),
            None,
        )
        if candidate_index is None:
            raise ValueError(f"unknown event candidate: {candidate_id}")
        candidate = candidates[candidate_index]
        if not candidate.radar_collection.complete:
            raise ValueError("event candidate review requires a complete radar window")
        if candidate.review is not None:
            if _same_review(
                candidate.review,
                decision=decision,
                reviewer=reviewer,
                weather_regime=weather_regime,
                official_context_references=official_context_references,
                official_context_inputs=context_inputs,
                notes=notes,
            ):
                return EventReviewResult(
                    catalog_path=catalog_path,
                    candidate_id=candidate_id,
                    decision=decision,
                    catalog_changed=False,
                )
            raise ValueError("event candidate already has a different human review")

        if official_context_references and not context_inputs:
            raise ValueError(
                "new official context references require checksummed artifact files"
            )
        if decision == "approved" and not context_inputs:
            raise ValueError(
                "approved review requires checksummed official context evidence"
            )

        official_context_artifacts = _persist_official_context(
            layout=layout,
            candidate_id=candidate_id,
            inputs=context_inputs,
            fetched_at=current_time,
        )

        review = EventReviewRecord(
            decision=decision,
            reviewer=reviewer,
            reviewed_at=iso_seconds(current_time),
            weather_regime=weather_regime,
            official_context_references=official_context_references,
            official_context_artifacts=official_context_artifacts,
            notes=notes,
        )
        candidates[candidate_index] = EventCandidate.model_validate(
            candidate.model_dump(mode="python")
            | {
                "review_status": decision,
                "weather_regime": weather_regime,
                "review": review,
            }
        )
        updated = EventEvidenceCatalog.model_validate(
            catalog.model_dump(mode="python")
            | {
                "updated_at": iso_seconds(current_time),
                "candidates": tuple(candidates),
            }
        )
        verification_errors = verify_event_evidence_catalog(updated, layout=layout)
        if verification_errors:
            raise RuntimeError(
                "event evidence catalog verification failed after review: "
                + "; ".join(verification_errors)
            )
        changed = write_schema_if_changed(catalog_path, updated)
        return EventReviewResult(
            catalog_path=catalog_path,
            candidate_id=candidate_id,
            decision=decision,
            catalog_changed=changed,
        )


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Record a human review for one completed event candidate.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=settings.research_root / "discovery" / "event_evidence_catalog.json",
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--decision", choices=DECISIONS, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--weather-regime", choices=WEATHER_REGIMES, required=True)
    parser.add_argument(
        "--official-context",
        action="append",
        default=[],
        help="Repeat for each official HTTPS weather-context source.",
    )
    parser.add_argument(
        "--official-context-file",
        action="append",
        type=Path,
        default=[],
        help="Repeat with the local file captured from each official context URL.",
    )
    parser.add_argument(
        "--official-context-publisher",
        action="append",
        default=[],
        help="Repeat with the publisher name for each official context file.",
    )
    parser.add_argument(
        "--official-context-published-at",
        action="append",
        default=[],
        help="Repeat with the timezone-aware publication time for each context file.",
    )
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    started_at, start_timer = start_run()
    try:
        result = review_event_candidate(
            catalog_path=args.catalog,
            repository_root=args.repository_root,
            candidate_id=args.candidate_id,
            decision=args.decision,
            reviewer=args.reviewer,
            weather_regime=args.weather_regime,
            official_context_references=tuple(args.official_context),
            official_context_files=tuple(args.official_context_file),
            official_context_publishers=tuple(args.official_context_publisher),
            official_context_published_at=tuple(args.official_context_published_at),
            notes=args.notes,
        )
    except Exception as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=str(exc),
            started_at=started_at,
            start_timer=start_timer,
            inputs={"catalog": str(args.catalog), "candidate_id": args.candidate_id},
            metadata={"decision": args.decision, "reviewer": args.reviewer},
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        LOGGER.error("event review failed: %s", exc)
        raise SystemExit(1) from exc

    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"catalog": str(args.catalog), "candidate_id": args.candidate_id},
        outputs={"event_evidence_catalog": str(result.catalog_path)},
        row_counts={"reviewed_candidates": 1 if result.catalog_changed else 0},
        metadata={
            "decision": result.decision,
            "reviewer": args.reviewer,
            "weather_regime": args.weather_regime,
            "official_context_reference_count": len(args.official_context),
            "official_context_artifact_count": len(args.official_context_file),
            "catalog_changed": result.catalog_changed,
            "formal_split_membership": "not_added",
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    LOGGER.info(
        "event review recorded: candidate=%s decision=%s catalog_changed=%s",
        result.candidate_id,
        result.decision,
        result.catalog_changed,
    )


if __name__ == "__main__":
    main()
