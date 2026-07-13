import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from minxionghydrocast.io.research_store import (
    ResearchLayout,
    artifact_record,
    atomic_write_schema,
)
from minxionghydrocast.models.dataset_schemas import RadarDatasetManifest
from minxionghydrocast.models.event_evidence_schemas import (
    CandidateRadarCollection,
    CoverageMetric,
    DiscoveryConfig,
    DiscoveryCursor,
    EventCandidate,
    EventEvidenceCatalog,
    EvidenceSourceRecord,
    RadarFrameMetric,
    SynchronizedEvidenceCapture,
)
from minxionghydrocast.pipelines.event_promotion import validate_candidate_promotion_gate
from minxionghydrocast.pipelines.event_review import review_event_candidate
from minxionghydrocast.pipelines.event_split_check import check_event_split_manifest

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
CANDIDATE_ID = "cwa_o_a0059_candidate_20260714t1010"
WINDOW_START = "2026-07-14T10:00:00+08:00"
TRIGGER_TIME = "2026-07-14T10:10:00+08:00"
WINDOW_END = "2026-07-14T10:20:00+08:00"


def write_artifact(layout: ResearchLayout, relative: str, content: str, kind: str):
    path = layout.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return artifact_record(layout, path, kind=kind)


def write_complete_catalog(
    tmp_path: Path,
    *,
    complete: bool = True,
) -> tuple[Path, Path, ResearchLayout]:
    repository = tmp_path / "repository"
    repository.mkdir()
    layout = ResearchLayout(tmp_path / "external-research")
    layout.ensure()
    plan = write_artifact(layout, "events/plan.json", "{}\n", "candidate_radar_plan")
    collection = write_artifact(
        layout,
        "events/collection.json",
        "{}\n",
        "candidate_radar_collection",
    )
    frames = tuple(
        write_artifact(
            layout,
            f"raw/event_evidence/{CANDIDATE_ID}/{minute}.json",
            f'{{"minute":"{minute}"}}\n',
            "candidate_radar_frame",
        )
        for minute in ("1000", "1010", "1020")
    )
    qpe = write_artifact(
        layout,
        f"evidence/{CANDIDATE_ID}/capture/O-B0045-001.json",
        "{}\n",
        "qpe_grid_evidence",
    )
    gauges = write_artifact(
        layout,
        f"evidence/{CANDIDATE_ID}/capture/O-A0002-001.json",
        "{}\n",
        "rain_gauge_evidence",
    )
    warnings = write_artifact(
        layout,
        f"evidence/{CANDIDATE_ID}/capture/WRA-Rainfall-Warning.json",
        "{}\n",
        "rainfall_warning_evidence",
    )
    metric = RadarFrameMetric(
        data_time=TRIGGER_TIME,
        source_sha256="a" * 64,
        source_bytes=100,
        threshold_dbz=35.0,
        local=CoverageMetric(
            valid_pixel_count=9,
            pixels_ge_threshold=1,
            fraction_ge_threshold=1 / 9,
            max_value=42.0,
        ),
        taiwan=CoverageMetric(
            valid_pixel_count=9,
            pixels_ge_threshold=1,
            fraction_ge_threshold=1 / 9,
            max_value=42.0,
        ),
        candidate_labels=("minxiong_35dbz",),
    )
    missing = () if complete else (WINDOW_END,)
    captured_frames = frames if complete else frames[:2]
    candidate = EventCandidate(
        candidate_id=CANDIDATE_ID,
        operational_status="awaiting_review" if complete else "collecting",
        first_trigger_time=TRIGGER_TIME,
        last_trigger_time=TRIGGER_TIME,
        window_start_time=WINDOW_START,
        window_end_time=WINDOW_END,
        candidate_labels=("minxiong_35dbz",),
        triggers=(metric,),
        radar_collection=CandidateRadarCollection(
            expected_frame_count=3,
            captured_frame_count=len(captured_frames),
            missing_data_times=missing,
            plan=plan,
            collection=collection,
            frames=captured_frames,
            complete=complete,
        ),
        evidence_captures=(
            SynchronizedEvidenceCapture(
                capture_id=f"{CANDIDATE_ID}_20260714t1010",
                target_data_time=TRIGGER_TIME,
                captured_at="2026-07-14T10:12:00+08:00",
                qpe=EvidenceSourceRecord(
                    dataset_id="O-B0045-001",
                    status="ok",
                    observed_at=TRIGGER_TIME,
                    alignment_delta_minutes=0.0,
                    artifact=qpe,
                ),
                gauges=EvidenceSourceRecord(
                    dataset_id="O-A0002-001",
                    status="ok",
                    observed_at=TRIGGER_TIME,
                    alignment_delta_minutes=0.0,
                    artifact=gauges,
                ),
                warnings=EvidenceSourceRecord(
                    dataset_id="WRA-Rainfall-Warning-v2",
                    status="empty",
                    artifact=warnings,
                ),
            ),
        ),
    )
    catalog = EventEvidenceCatalog(
        updated_at="2026-07-14T10:12:00+08:00",
        research_root=str(layout.root),
        config=DiscoveryConfig(
            initial_lookback_minutes=20,
            merge_gap_minutes=10,
            before_minutes=10,
            after_minutes=10,
        ),
        cursor=DiscoveryCursor(
            last_scanned_data_time=TRIGGER_TIME,
            last_successful_scan_at="2026-07-14T10:12:00+08:00",
        ),
        candidates=(candidate,),
    )
    catalog_path = layout.discovery / "event_evidence_catalog.json"
    atomic_write_schema(catalog_path, catalog)
    return catalog_path, repository, layout


def formal_manifest(*, event_type: str = "convective") -> RadarDatasetManifest:
    definitions = [
        (
            CANDIDATE_ID,
            "train",
            "Minxiong, Chiayi County",
            WINDOW_START,
            WINDOW_END,
            CANDIDATE_ID,
            event_type,
        ),
        (
            "train_two",
            "train",
            "Taiwan",
            "2026-07-15T10:00:00+08:00",
            "2026-07-15T12:00:00+08:00",
            None,
            "radar_candidate",
        ),
        (
            "validation_one",
            "validation",
            "Taiwan",
            "2026-07-16T10:00:00+08:00",
            "2026-07-16T12:00:00+08:00",
            None,
            "radar_candidate",
        ),
        (
            "test_one",
            "test",
            "Minxiong, Chiayi County",
            "2026-07-17T10:00:00+08:00",
            "2026-07-17T12:00:00+08:00",
            None,
            "radar_candidate",
        ),
        (
            "test_two",
            "test",
            "Minxiong, Chiayi County",
            "2026-07-18T10:00:00+08:00",
            "2026-07-18T12:00:00+08:00",
            None,
            "radar_candidate",
        ),
    ]
    events = []
    splits = {"train": [], "validation": [], "test": []}
    for event_id, split, region, start, end, candidate_id, kind in definitions:
        events.append(
            {
                "event_id": event_id,
                "name": event_id,
                "event_type": kind,
                "region": region,
                "start_time": start,
                "end_time": end,
                "source": "CWA O-A0059-001 event evidence",
                "evidence_candidate_id": candidate_id,
            }
        )
        splits[split].append(event_id)
    return RadarDatasetManifest.model_validate(
        {
            "schema_version": "2.0",
            "split_strategy": "event_based",
            "target": "radar_nowcasting",
            "dataset": {
                "data_id": "O-A0059-001",
                "input_length": 6,
                "prediction_length": 6,
                "cadence_minutes": 10,
                "minimum_counts": {
                    "train": 2,
                    "validation": 1,
                    "test": 2,
                    "minxiong_test": 2,
                },
            },
            "events": events,
            "splits": splits,
        }
    )


def approve_candidate(catalog_path: Path, repository: Path) -> None:
    review_event_candidate(
        catalog_path=catalog_path,
        repository_root=repository,
        candidate_id=CANDIDATE_ID,
        decision="approved",
        reviewer="data-contract-reviewer@example.test",
        weather_regime="convective",
        official_context_references=("https://www.cwa.gov.tw/official-context",),
        notes="Reviewed radar, QPE, gauges, warnings, and official context.",
        now=datetime(2026, 7, 14, 12, 0, tzinfo=TAIPEI_TZ),
    )


def test_event_review_records_provenance_and_is_idempotent(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path)

    approve_candidate(catalog_path, repository)
    reviewed_bytes = catalog_path.read_bytes()
    result = review_event_candidate(
        catalog_path=catalog_path,
        repository_root=repository,
        candidate_id=CANDIDATE_ID,
        decision="approved",
        reviewer="data-contract-reviewer@example.test",
        weather_regime="convective",
        official_context_references=("https://www.cwa.gov.tw/official-context",),
        notes="Reviewed radar, QPE, gauges, warnings, and official context.",
        now=datetime(2026, 7, 14, 12, 5, tzinfo=TAIPEI_TZ),
    )

    catalog = EventEvidenceCatalog.model_validate_json(reviewed_bytes)
    candidate = catalog.candidates[0]
    assert result.catalog_changed is False
    assert catalog_path.read_bytes() == reviewed_bytes
    assert candidate.review_status == "approved"
    assert candidate.weather_regime == "convective"
    assert candidate.review is not None
    assert candidate.review.reviewer == "data-contract-reviewer@example.test"
    assert candidate.review.reviewed_at == "2026-07-14T12:00:00+08:00"
    assert candidate.formal_split_membership == "not_added"


def test_event_review_rejects_incomplete_window(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path, complete=False)

    with pytest.raises(ValueError, match="complete radar window"):
        review_event_candidate(
            catalog_path=catalog_path,
            repository_root=repository,
            candidate_id=CANDIDATE_ID,
            decision="rejected",
            reviewer="reviewer@example.test",
            weather_regime="unclassified",
            now=datetime(2026, 7, 14, 12, 0, tzinfo=TAIPEI_TZ),
        )


def test_event_review_approval_requires_official_context(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path)

    with pytest.raises(ValueError, match="official context evidence"):
        review_event_candidate(
            catalog_path=catalog_path,
            repository_root=repository,
            candidate_id=CANDIDATE_ID,
            decision="approved",
            reviewer="reviewer@example.test",
            weather_regime="convective",
            now=datetime(2026, 7, 14, 12, 0, tzinfo=TAIPEI_TZ),
        )


def test_dataset_candidate_promotion_requires_approved_review(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path)
    manifest = formal_manifest()

    with pytest.raises(ValueError, match="lacks an approved human review"):
        validate_candidate_promotion_gate(
            manifest=manifest,
            event_evidence_catalog_path=catalog_path,
            repository_root=repository,
        )

    approve_candidate(catalog_path, repository)
    validate_candidate_promotion_gate(
        manifest=manifest,
        event_evidence_catalog_path=catalog_path,
        repository_root=repository,
    )


def test_dataset_candidate_promotion_requires_evidence_catalog(tmp_path: Path):
    _catalog_path, repository, _layout = write_complete_catalog(tmp_path)

    with pytest.raises(ValueError, match="no event evidence catalog was provided"):
        validate_candidate_promotion_gate(
            manifest=formal_manifest(),
            event_evidence_catalog_path=None,
            repository_root=repository,
        )


def test_dataset_candidate_promotion_rejects_corrupt_evidence(tmp_path: Path):
    catalog_path, repository, layout = write_complete_catalog(tmp_path)
    approve_candidate(catalog_path, repository)
    catalog = EventEvidenceCatalog.model_validate_json(
        catalog_path.read_text(encoding="utf-8")
    )
    qpe_artifact = catalog.candidates[0].evidence_captures[0].qpe.artifact
    assert qpe_artifact is not None
    (layout.root / qpe_artifact.path).write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed checksum verification"):
        validate_candidate_promotion_gate(
            manifest=formal_manifest(),
            event_evidence_catalog_path=catalog_path,
            repository_root=repository,
        )


def test_dataset_candidate_promotion_rejects_regime_mismatch(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path)
    approve_candidate(catalog_path, repository)

    with pytest.raises(ValueError, match="event_type must match reviewed regime"):
        validate_candidate_promotion_gate(
            manifest=formal_manifest(event_type="front"),
            event_evidence_catalog_path=catalog_path,
            repository_root=repository,
        )


def test_dataset_candidate_promotion_rejects_window_mismatch(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path)
    approve_candidate(catalog_path, repository)
    payload = formal_manifest().model_dump(mode="json")
    payload["events"][0]["start_time"] = "2026-07-14T09:50:00+08:00"
    manifest = RadarDatasetManifest.model_validate(payload)

    with pytest.raises(ValueError, match="start_time does not match reviewed candidate"):
        validate_candidate_promotion_gate(
            manifest=manifest,
            event_evidence_catalog_path=catalog_path,
            repository_root=repository,
        )


def test_event_split_check_enforces_candidate_review_gate(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path)
    manifest_path = repository / "event_split_manifest.json"
    manifest_path.write_text(
        formal_manifest().model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    pending = check_event_split_manifest(
        manifest_path=manifest_path,
        event_evidence_catalog_path=catalog_path,
        repository_root=repository,
    )
    assert pending["status"] == "error"
    assert pending["candidate_promotion_gate"] == "error"
    assert any("lacks an approved human review" in error for error in pending["errors"])

    approve_candidate(catalog_path, repository)
    approved = check_event_split_manifest(
        manifest_path=manifest_path,
        event_evidence_catalog_path=catalog_path,
        repository_root=repository,
    )
    assert approved["status"] == "ok"
    assert approved["candidate_promotion_gate"] == "ok"


def test_dataset_manifest_requires_candidate_reference():
    payload = formal_manifest().model_dump(mode="json")
    payload["events"][0]["evidence_candidate_id"] = None

    with pytest.raises(ValueError, match="requires evidence_candidate_id"):
        RadarDatasetManifest.model_validate(payload)


def test_review_catalog_json_has_no_untyped_manual_fields(tmp_path: Path):
    catalog_path, repository, _layout = write_complete_catalog(tmp_path)
    approve_candidate(catalog_path, repository)

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert payload["candidates"][0]["review"] == {
        "decision": "approved",
        "reviewer": "data-contract-reviewer@example.test",
        "reviewed_at": "2026-07-14T12:00:00+08:00",
        "weather_regime": "convective",
        "official_context_references": ["https://www.cwa.gov.tw/official-context"],
        "notes": "Reviewed radar, QPE, gauges, warnings, and official context.",
    }
