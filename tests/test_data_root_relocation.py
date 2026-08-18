import hashlib
from pathlib import Path

import pytest

from minxionghydrocast.ingestion.cwa_event_collector import CwaEventCollection
from minxionghydrocast.io.data_store import (
    DataLayout,
    artifact_record,
    atomic_write_schema,
    sha256_file,
)
from minxionghydrocast.models.dataset_schemas import ArtifactRecord, DatasetCatalog
from minxionghydrocast.models.event_evidence_schemas import (
    CandidateRadarCollection,
    CoverageMetric,
    DiscoveryConfig,
    DiscoveryCursor,
    EventCandidate,
    EventEvidenceCatalog,
    RadarFrameMetric,
)
from minxionghydrocast.operations.data_root_relocation import (
    DataRootRelocationError,
    apply_data_root_relocation,
    plan_data_root_relocation,
)


def _record(layout: DataLayout, path: Path, kind: str) -> ArtifactRecord:
    return artifact_record(layout, path, kind=kind)


def _metric() -> RadarFrameMetric:
    coverage = CoverageMetric(
        valid_pixel_count=1,
        pixels_ge_threshold=1,
        fraction_ge_threshold=1.0,
        max_value=40.0,
    )
    return RadarFrameMetric(
        data_time="2026-08-18T10:00:00+08:00",
        source_sha256="a" * 64,
        source_bytes=1,
        threshold_dbz=35.0,
        local=coverage,
        taiwan=coverage,
        candidate_labels=("minxiong_35dbz",),
    )


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    manifest = repository / "manifest.json"
    manifest.write_bytes(b'{"tracked": true}\n')

    old_root = tmp_path / "old-data-root"
    new_root = tmp_path / "new-data-root"
    layout = DataLayout(new_root)
    layout.ensure()

    frame = layout.raw / "event_evidence" / "frame.json"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"frame-payload\n")
    plan = layout.events / "candidate_plan.json"
    plan.write_bytes(b"{}\n")
    collection_path = layout.events / "candidate_collection.json"
    collection = CwaEventCollection.model_validate(
        {
            "event_id": "candidate_20260818",
            "data_id": "O-A0059-001",
            "frame_count": 1,
            "bytes_written": frame.stat().st_size,
            "frames": (
                {
                    "data_time": "2026-08-18T10:00:00+08:00",
                    "source_url": "https://example.test/frame.json",
                    "output_path": str(old_root / "raw/event_evidence/frame.json"),
                    "bytes_written": frame.stat().st_size,
                },
            ),
        }
    )
    atomic_write_schema(collection_path, collection)

    candidate = EventCandidate(
        candidate_id="candidate_20260818",
        operational_status="awaiting_review",
        first_trigger_time="2026-08-18T10:00:00+08:00",
        last_trigger_time="2026-08-18T10:00:00+08:00",
        window_start_time="2026-08-18T09:50:00+08:00",
        window_end_time="2026-08-18T10:10:00+08:00",
        candidate_labels=("minxiong_35dbz",),
        triggers=(_metric(),),
        radar_collection=CandidateRadarCollection(
            expected_frame_count=1,
            captured_frame_count=1,
            missing_data_times=(),
            plan=_record(layout, plan, "candidate_radar_plan"),
            collection=_record(layout, collection_path, "candidate_radar_collection"),
            frames=(_record(layout, frame, "candidate_radar_frame"),),
            complete=True,
        ),
    )
    event_catalog = EventEvidenceCatalog(
        updated_at="2026-08-18T10:12:00+08:00",
        data_root=str(old_root),
        config=DiscoveryConfig(),
        cursor=DiscoveryCursor(),
        candidates=(candidate,),
    )
    atomic_write_schema(layout.discovery / "event_evidence_catalog.json", event_catalog)

    history = layout.discovery_history / "history.json"
    history.write_bytes(b"history\n")
    archives: dict[str, ArtifactRecord] = {}
    for split in ("train", "validation", "test"):
        archive = layout.tensors / f"{split}.npz"
        archive.write_bytes(f"{split}\n".encode())
        archives[split] = _record(layout, archive, "combined_tensor_archive")
    dataset_catalog = DatasetCatalog(
        generated_at="2026-08-18T10:12:00+08:00",
        data_root=str(old_root),
        dataset_id="fixture",
        source_data_id="O-A0059-001",
        manifest=ArtifactRecord(
            kind="tracked_dataset_manifest",
            path=str(manifest),
            sha256=sha256_file(manifest),
            bytes=manifest.stat().st_size,
        ),
        history_index=_record(layout, history, "history_index"),
        split_counts={"train": 0, "validation": 0, "test": 0},
        events=[],
        combined_archives=archives,
        forecast_publication_ready=False,
        forecast_publication_blockers=["fixture is not publishable"],
    )
    atomic_write_schema(layout.catalog / "dataset_catalog.json", dataset_catalog)
    return repository, old_root, new_root, frame


def test_data_root_relocation_rewrites_catalogs_collections_and_verification(tmp_path: Path):
    repository, old_root, new_root, frame = _write_fixture(tmp_path)
    collection_path = new_root / "events/candidate_collection.json"
    event_catalog_path = new_root / "discovery/event_evidence_catalog.json"

    plan = plan_data_root_relocation(
        old_root=old_root,
        new_root=new_root,
        repository_root=repository,
    )

    assert plan.collection_documents == 1
    assert plan.collection_frame_paths == 1
    assert plan.catalog_documents == 2
    assert plan.refreshed_artifact_checksums == 1
    assert collection_path.read_text().find(str(old_root)) != -1
    assert event_catalog_path.read_text().find(str(old_root)) != -1

    backup_dir = apply_data_root_relocation(plan)

    assert backup_dir is not None
    assert (backup_dir / "events/candidate_collection.json").is_file()
    relocated_collection = CwaEventCollection.model_validate_json(collection_path.read_text())
    assert relocated_collection.frames[0].output_path == str(frame)
    relocated_event_catalog = EventEvidenceCatalog.model_validate_json(event_catalog_path.read_text())
    assert relocated_event_catalog.data_root == str(new_root.resolve())
    collection_artifact = relocated_event_catalog.candidates[0].radar_collection.collection
    assert collection_artifact is not None
    assert collection_artifact.sha256 == sha256_file(collection_path)
    relocated_dataset_catalog = DatasetCatalog.model_validate_json(
        (new_root / "catalog/dataset_catalog.json").read_text()
    )
    assert relocated_dataset_catalog.data_root == str(new_root.resolve())
    verification = (new_root / "catalog/dataset_verification.json").read_text()
    assert '"status": "ok"' in verification
    assert hashlib.sha256(
        (new_root / "catalog/dataset_catalog.json").read_bytes()
    ).hexdigest() in verification

    repeated = plan_data_root_relocation(
        old_root=old_root,
        new_root=new_root,
        repository_root=repository,
    )
    assert repeated.changes == ()


def test_data_root_relocation_rejects_unrelated_checksum_mismatches(tmp_path: Path):
    repository, old_root, new_root, frame = _write_fixture(tmp_path)
    frame.write_bytes(b"unexpected content\n")

    with pytest.raises(
        DataRootRelocationError,
        match="not caused by a rewritten collection",
    ):
        plan_data_root_relocation(
            old_root=old_root,
            new_root=new_root,
            repository_root=repository,
        )

    refreshed = plan_data_root_relocation(
        old_root=old_root,
        new_root=new_root,
        repository_root=repository,
        refresh_artifact_checksums=True,
    )
    assert refreshed.refreshed_artifact_checksums == 2
