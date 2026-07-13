import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from minxionghydrocast.ingestion.cwa_history import CwaHistoryFile, CwaHistoryIndex
from minxionghydrocast.ingestion.source_adapter import SourceProvenance, SourceResult
from minxionghydrocast.models.event_evidence_schemas import (
    DiscoveryConfig,
    EventEvidenceCatalog,
)
from minxionghydrocast.io.research_store import ResearchLayout, sha256_file
from minxionghydrocast.pipelines.event_discovery import (
    run_event_discovery,
    verify_event_evidence_catalog,
)
from minxionghydrocast.pipelines.event_review import review_event_candidate

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


class FakeResponse:
    def __init__(self, content: bytes, url: str):
        self.content = content
        self.url = url
        self.status_code = 200
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        return None


def grid_bytes(
    *,
    data_id: str,
    data_time: str,
    values: list[float],
    units: str,
) -> bytes:
    parameter_name = "Reflectivity" if units == "dBZ" else "Precipitation"
    payload = {
        "cwaopendata": {
            "sent": data_time,
            "dataid": data_id,
            "source": "CWA",
            "dataset": {
                "datasetInfo": {
                    "datasetDescription": "synthetic official-contract grid",
                    "parameterSet": {
                        "StartPointLongitude": "120.425",
                        "StartPointLatitude": "23.545",
                        "GridResolution": "0.005",
                        "DateTime": data_time,
                        "GridDimensionX": "3",
                        "GridDimensionY": "3",
                        parameter_name: units,
                    },
                },
                "contents": {
                    "contentDescription": (
                        "資料無效值為-99，觀測範圍外以-999表示。"
                        "使用之座標系統為TWD67。"
                    ),
                    "content": ",".join(str(value) for value in values),
                },
            },
        }
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def history_index(times: list[str]) -> CwaHistoryIndex:
    files = tuple(
        CwaHistoryFile(
            data_time=value,
            url=f"https://example.test/{value[11:16].replace(':', '')}.json",
            filename=f"{value[11:16].replace(':', '')}.json",
            file_format="JSON",
            size="1000",
            raw={"dataTime": value},
        )
        for value in times
    )
    return CwaHistoryIndex(
        data_id="O-A0059-001",
        source_url="https://example.test/history?Authorization=REDACTED",
        files=files,
        raw={"synthetic": True},
        file_count=len(files),
    )


def source_result(
    *,
    dataset: str,
    dataset_id: str,
    outcome: str,
    observed_at: str | None,
) -> SourceResult:
    records = [] if outcome == "empty" else [{"水情時間ISO": str(observed_at), "值": "1"}]
    return SourceResult(
        dataset=dataset,
        records=records,
        provenance=SourceProvenance(
            source_kind="api",
            outcome=outcome,
            authority="official test authority",
            dataset_id=dataset_id,
            source_url="https://example.test/official",
            fetched_at="2026-07-14T10:12:00+08:00",
            schema_version="test-v1",
            content_sha256="a" * 64,
        ),
    )


def test_event_discovery_resumes_window_and_is_idempotent(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    manifest = repository / "data" / "samples" / "event_split_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"formal":"unchanged"}\n', encoding="utf-8")
    manifest_before = hashlib.sha256(manifest.read_bytes()).hexdigest()
    research = tmp_path / "external-research"
    times = [
        "2026-07-14T10:00:00+08:00",
        "2026-07-14T10:10:00+08:00",
        "2026-07-14T10:20:00+08:00",
    ]
    radar_payloads = {
        "1000.json": grid_bytes(
            data_id="O-A0059-001",
            data_time=times[0],
            values=[1] * 9,
            units="dBZ",
        ),
        "1010.json": grid_bytes(
            data_id="O-A0059-001",
            data_time=times[1],
            values=[1, 1, 1, 1, 40, 1, 1, 1, 1],
            units="dBZ",
        ),
        "1020.json": grid_bytes(
            data_id="O-A0059-001",
            data_time=times[2],
            values=[2] * 9,
            units="dBZ",
        ),
    }
    frame_requests: list[str] = []

    def frame_get(url: str, *, timeout: int, verify: bool) -> FakeResponse:
        name = Path(urlsplit(url).path).name
        frame_requests.append(name)
        return FakeResponse(radar_payloads[name], url)

    qpe = grid_bytes(
        data_id="O-B0045-001",
        data_time=times[1],
        values=[0, 0, 0, 0, 5, 0, 0, 0, 0],
        units="mm",
    )

    def qpe_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> FakeResponse:
        return FakeResponse(qpe, f"{url}?Authorization={params['Authorization']}")

    config = DiscoveryConfig(
        local_radius_pixels=0,
        local_min_pixels=1,
        taiwan_min_pixels=2,
        initial_lookback_minutes=20,
        merge_gap_minutes=10,
        before_minutes=10,
        after_minutes=10,
    )
    common = {
        "repository_root": repository,
        "research_root": research,
        "cwa_api_key": "cwa-secret",
        "wra_api_key": "wra-secret",
        "config": config,
        "timeout": 1,
        "retry_backoff_seconds": 0.0,
        "frame_http_get": frame_get,
        "qpe_http_get": qpe_get,
        "gauge_collector": lambda: source_result(
            dataset="rain_gauges",
            dataset_id="O-A0002-001",
            outcome="ok",
            observed_at=times[1],
        ),
        "warning_collector": lambda: source_result(
            dataset="rainfall_alerts",
            dataset_id="WRA-Rainfall-Warning-v2",
            outcome="empty",
            observed_at=None,
        ),
    }

    first = run_event_discovery(
        **common,
        history_index=history_index(times[:2]),
        now=datetime(2026, 7, 14, 10, 12, tzinfo=TAIPEI_TZ),
    )
    first_catalog = EventEvidenceCatalog.model_validate_json(
        first.catalog_path.read_text(encoding="utf-8")
    )
    assert first.scanned_frame_count == 2
    assert first.trigger_frame_count == 1
    assert first.candidate_count == 1
    assert first_catalog.candidates[0].operational_status == "collecting"
    assert first_catalog.candidates[0].radar_collection.captured_frame_count == 2
    assert first_catalog.candidates[0].radar_collection.missing_data_times == (times[2],)

    second = run_event_discovery(
        **common,
        history_index=history_index(times),
        now=datetime(2026, 7, 14, 10, 22, tzinfo=TAIPEI_TZ),
    )
    second_bytes = second.catalog_path.read_bytes()
    catalog = EventEvidenceCatalog.model_validate_json(second_bytes)
    candidate = catalog.candidates[0]
    assert second.catalog_changed is True
    assert second.scanned_frame_count == 1
    assert candidate.operational_status == "awaiting_review"
    assert candidate.review_status == "pending"
    assert candidate.formal_split_membership == "not_added"
    assert candidate.weather_regime == "unclassified"
    assert candidate.radar_collection.complete is True
    assert candidate.radar_collection.captured_frame_count == 3
    assert len(candidate.evidence_captures) == 1
    capture = candidate.evidence_captures[0]
    assert capture.qpe.status == "ok"
    assert capture.gauges.status == "ok"
    assert capture.warnings.status == "empty"
    assert all(
        source.artifact is not None
        for source in (capture.qpe, capture.gauges, capture.warnings)
    )

    requests_before_rerun = list(frame_requests)
    noisy_history = history_index(times)
    noisy_history = noisy_history.model_copy(
        update={
            "raw": {"request_id": "changes-without-changing-files"},
            "files": tuple(
                item.model_copy(update={"raw": {"response_wrapper": "changed"}})
                for item in noisy_history.files
            ),
        }
    )
    third = run_event_discovery(
        **common,
        history_index=noisy_history,
        now=datetime(2026, 7, 14, 10, 24, tzinfo=TAIPEI_TZ),
    )
    assert third.catalog_changed is False
    assert third.scanned_frame_count == 0
    assert third.catalog_path.read_bytes() == second_bytes
    assert frame_requests == requests_before_rerun
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == manifest_before

    frame_artifact = candidate.radar_collection.frames[-1]
    frame_path = research / frame_artifact.path
    frame_path.write_bytes(b"corrupt")
    fourth = run_event_discovery(
        **common,
        history_index=history_index(times),
        now=datetime(2026, 7, 14, 10, 26, tzinfo=TAIPEI_TZ),
    )
    assert fourth.catalog_changed is False
    assert frame_requests[-1] == "1020.json"
    assert sha256_file(frame_path) == frame_artifact.sha256
    assert fourth.catalog_path.read_bytes() == second_bytes

    review_event_candidate(
        catalog_path=fourth.catalog_path,
        repository_root=repository,
        candidate_id=candidate.candidate_id,
        decision="approved",
        reviewer="reviewer@example.test",
        weather_regime="convective",
        official_context_references=("https://www.cwa.gov.tw/official-context",),
        now=datetime(2026, 7, 14, 10, 27, tzinfo=TAIPEI_TZ),
    )
    gauge_artifact = capture.gauges.artifact
    assert gauge_artifact is not None
    gauge_path = research / gauge_artifact.path
    gauge_path.write_bytes(b"corrupt")
    fifth = run_event_discovery(
        **common,
        history_index=history_index(times),
        now=datetime(2026, 7, 14, 10, 28, tzinfo=TAIPEI_TZ),
    )
    repaired_catalog = EventEvidenceCatalog.model_validate_json(
        fifth.catalog_path.read_text(encoding="utf-8")
    )
    assert fifth.catalog_changed is True
    assert fifth.evidence_error_count == 0
    assert repaired_catalog.candidates[0].review_status == "approved"
    assert verify_event_evidence_catalog(
        repaired_catalog,
        layout=ResearchLayout(research),
    ) == ()

    sixth = run_event_discovery(
        **common,
        history_index=history_index(times),
        now=datetime(2026, 7, 14, 10, 30, tzinfo=TAIPEI_TZ),
    )
    assert sixth.catalog_changed is False


def test_catalog_contract_rejects_automatic_formal_split_updates():
    payload = {
        "schema_version": "1.0",
        "updated_at": "2026-07-14T10:00:00+08:00",
        "research_root": "/external/research",
        "config": DiscoveryConfig().model_dump(mode="json"),
        "cursor": {
            "last_scanned_data_time": None,
            "last_successful_scan_at": None,
        },
        "candidate_queue_only": True,
        "automatic_formal_split_updates": True,
        "retraining_policy": "only_after_human_approved_new_events",
        "history_indexes": [],
        "candidates": [],
    }

    with pytest.raises(ValidationError):
        EventEvidenceCatalog.model_validate(payload)


def test_event_discovery_retries_failed_synchronized_evidence(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    research = tmp_path / "external-research"
    data_time = "2026-07-14T10:10:00+08:00"
    radar = grid_bytes(
        data_id="O-A0059-001",
        data_time=data_time,
        values=[1, 1, 1, 1, 40, 1, 1, 1, 1],
        units="dBZ",
    )
    qpe = grid_bytes(
        data_id="O-B0045-001",
        data_time=data_time,
        values=[0] * 9,
        units="mm",
    )

    def frame_get(url: str, *, timeout: int, verify: bool) -> FakeResponse:
        return FakeResponse(radar, url)

    def qpe_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> FakeResponse:
        return FakeResponse(qpe, url)

    warning_attempts = 0

    def warning_collector() -> SourceResult:
        nonlocal warning_attempts
        warning_attempts += 1
        if warning_attempts == 1:
            raise RuntimeError("temporary warning source failure")
        return source_result(
            dataset="rainfall_alerts",
            dataset_id="WRA-Rainfall-Warning-v2",
            outcome="empty",
            observed_at=None,
        )

    common = {
        "repository_root": repository,
        "research_root": research,
        "cwa_api_key": "cwa-secret",
        "wra_api_key": "wra-secret",
        "config": DiscoveryConfig(
            local_radius_pixels=0,
            taiwan_min_pixels=2,
            initial_lookback_minutes=10,
            merge_gap_minutes=10,
            before_minutes=10,
            after_minutes=10,
        ),
        "history_index": history_index([data_time]),
        "timeout": 1,
        "retry_backoff_seconds": 0.0,
        "frame_http_get": frame_get,
        "qpe_http_get": qpe_get,
        "gauge_collector": lambda: source_result(
            dataset="rain_gauges",
            dataset_id="O-A0002-001",
            outcome="ok",
            observed_at=data_time,
        ),
        "warning_collector": warning_collector,
    }

    first = run_event_discovery(
        **common,
        now=datetime(2026, 7, 14, 10, 12, tzinfo=TAIPEI_TZ),
    )
    assert first.evidence_error_count == 1

    second = run_event_discovery(
        **common,
        now=datetime(2026, 7, 14, 10, 14, tzinfo=TAIPEI_TZ),
    )
    catalog = EventEvidenceCatalog.model_validate_json(
        second.catalog_path.read_text(encoding="utf-8")
    )
    assert second.evidence_error_count == 0
    assert catalog.candidates[0].evidence_captures[0].warnings.status == "empty"
    assert warning_attempts == 2

    third = run_event_discovery(
        **common,
        now=datetime(2026, 7, 14, 10, 16, tzinfo=TAIPEI_TZ),
    )
    assert third.catalog_changed is False
    assert warning_attempts == 2
