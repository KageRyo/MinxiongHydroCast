from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from floodcasttw.ingestion.cwa_event_collector import (
    authorize_url,
    build_event_plan,
    download_event_frames,
)


class FakeResponse:
    def __init__(self, content: bytes, url: str, status_code: int = 200):
        self.content = content
        self.url = url
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def sample_history_index():
    return {
        "data_id": "O-A0059-001",
        "files": [
            {
                "data_time": "2026-07-06T19:40:00+08:00",
                "url": "https://example.test/1940.json?Authorization=CWA-FAKE-KEY",
                "filename": "1940.json",
                "file_format": "JSON",
            },
            {
                "data_time": "2026-07-06T19:20:00+08:00",
                "url": "https://example.test/1920.json",
                "filename": "1920.json",
                "file_format": "JSON",
            },
            {
                "data_time": "2026-07-06T19:30:00+08:00",
                "url": "https://example.test/1930.json",
                "filename": "1930.json",
                "file_format": "JSON",
            },
        ],
    }


def test_build_event_plan_selects_sorted_frames_in_window():
    plan = build_event_plan(
        sample_history_index(),
        event_id="chiayi_20260706_evening",
        start_time="2026-07-06T19:25:00+08:00",
        end_time="2026-07-06T19:45:00+08:00",
    )

    assert plan.event_id == "chiayi_20260706_evening"
    assert plan.data_id == "O-A0059-001"
    assert plan.frame_count == 2
    assert [frame.data_time for frame in plan.frames] == [
        "2026-07-06T19:30:00+08:00",
        "2026-07-06T19:40:00+08:00",
    ]
    assert "Authorization=REDACTED" in plan.frames[1].url
    assert "CWA-FAKE-KEY" not in plan.frames[1].url


def test_build_event_plan_applies_limit_after_sorting():
    plan = build_event_plan(
        sample_history_index(),
        event_id="limited",
        start_time="2026-07-06T19:00:00+08:00",
        end_time="2026-07-06T20:00:00+08:00",
        limit=2,
    )

    assert plan.frame_count == 2
    assert [frame.filename for frame in plan.frames] == ["1920.json", "1930.json"]


def test_build_event_plan_applies_frame_stride_after_sorting():
    plan = build_event_plan(
        sample_history_index(),
        event_id="stride",
        start_time="2026-07-06T19:00:00+08:00",
        end_time="2026-07-06T20:00:00+08:00",
        frame_stride=2,
    )

    assert plan.frame_count == 2
    assert [frame.filename for frame in plan.frames] == ["1920.json", "1940.json"]


def test_build_event_plan_rejects_reversed_time_window():
    try:
        build_event_plan(
            sample_history_index(),
            event_id="bad",
            start_time="2026-07-06T20:00:00+08:00",
            end_time="2026-07-06T19:00:00+08:00",
        )
    except ValueError as exc:
        assert "end_time" in str(exc)
    else:
        raise AssertionError("expected reversed window to fail")


def test_authorize_url_replaces_redacted_authorization():
    url = authorize_url(
        "https://example.test/file.json?Authorization=REDACTED&format=JSON",
        authorization="real-key",
    )
    query = parse_qs(urlsplit(url).query)

    assert query["Authorization"] == ["real-key"]
    assert query["format"] == ["JSON"]


def test_download_event_frames_writes_outputs_without_storing_key(tmp_path: Path):
    requested_urls = []

    def fake_get(url: str, *, timeout: int, verify: bool) -> FakeResponse:
        requested_urls.append(url)
        return FakeResponse(b'{"ok": true}', url)

    plan = build_event_plan(
        sample_history_index(),
        event_id="chiayi_20260706_evening",
        start_time="2026-07-06T19:30:00+08:00",
        end_time="2026-07-06T19:40:00+08:00",
    )

    collection = download_event_frames(
        plan,
        output_dir=tmp_path,
        authorization="real-key",
        http_get=fake_get,
    )

    assert collection.frame_count == 2
    assert collection.bytes_written == len(b'{"ok": true}') * 2
    assert len(requested_urls) == 2
    assert all("Authorization=real-key" in url for url in requested_urls)
    assert all("real-key" not in frame.source_url for frame in collection.frames)
    assert all(Path(frame.output_path).exists() for frame in collection.frames)


def test_download_event_frames_can_skip_existing_outputs(tmp_path: Path):
    plan = build_event_plan(
        sample_history_index(),
        event_id="chiayi_20260706_evening",
        start_time="2026-07-06T19:20:00+08:00",
        end_time="2026-07-06T19:20:00+08:00",
    )
    output = tmp_path / plan.event_id / "1920.json"
    output.parent.mkdir(parents=True)
    output.write_bytes(b'{"cached": true}')

    def fake_get(url: str, *, timeout: int, verify: bool) -> FakeResponse:
        raise AssertionError("skip_existing should not request cached frames")

    collection = download_event_frames(
        plan,
        output_dir=tmp_path,
        authorization="real-key",
        http_get=fake_get,
        skip_existing=True,
    )

    assert collection.frame_count == 1
    assert collection.frames[0].bytes_written == len(b'{"cached": true}')
    assert "real-key" not in collection.frames[0].source_url
