from urllib.parse import parse_qs, urlsplit

from floodcasttw.ingestion.cwa_history import (
    CwaHistoryRequest,
    dry_run_index,
    extract_history_files,
    fetch_history_index,
    redact_authorization_url,
    sanitize_cwa_payload,
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


def test_history_request_builds_redacted_url():
    request = CwaHistoryRequest(
        data_id="O-A0059-001",
        base_url="https://example.test/historyapi/v1/getMetadata",
    )
    query = parse_qs(urlsplit(request.redacted_url()).query)

    assert request.endpoint == "https://example.test/historyapi/v1/getMetadata/O-A0059-001"
    assert request.params(authorization="key") == {"Authorization": "key"}
    assert query["Authorization"] == ["REDACTED"]


def test_redact_authorization_url_keeps_regular_params():
    url = redact_authorization_url(
        "https://example.test/path?Authorization=real-key&format=JSON"
    )
    query = parse_qs(urlsplit(url).query)

    assert query["Authorization"] == ["REDACTED"]
    assert query["format"] == ["JSON"]
    assert "real-key" not in url


def test_extract_history_files_from_nested_metadata():
    payload = {
        "records": {
            "locations": [
                {
                    "dataTime": "2026-07-06T19:30:00+08:00",
                    "downloadURL": "https://example.test/a.json",
                    "fileName": "O-A0059-001-202607061930.json",
                    "format": "JSON",
                    "fileSize": "1234",
                },
                {
                    "DateTime": "2026-07-06T19:20:00+08:00",
                    "URL": "https://example.test/b.json",
                },
                {
                    "DateTime": "2026-07-06T19:10:00+08:00",
                    "ProductURL": (
                        "https://example.test/c.json?Authorization=CWA-FAKE-KEY"
                    ),
                },
                {
                    "dataTime": [
                        {
                            "DateTime": "2026-07-06T19:00:00+08:00",
                            "ProductURL": "https://example.test/d.json",
                        }
                    ]
                },
            ]
        }
    }

    files = extract_history_files(payload)

    assert len(files) == 4
    assert files[0].data_time == "2026-07-06T19:30:00+08:00"
    assert files[0].url == "https://example.test/a.json"
    assert files[0].filename == "O-A0059-001-202607061930.json"
    assert files[0].file_format == "JSON"
    assert files[0].size == "1234"
    assert files[1].data_time == "2026-07-06T19:20:00+08:00"
    assert files[1].url == "https://example.test/b.json"
    assert files[2].data_time == "2026-07-06T19:10:00+08:00"
    assert "Authorization=REDACTED" in files[2].url
    assert "CWA-FAKE-KEY" not in str(files[2].raw)
    assert files[3].data_time == "2026-07-06T19:00:00+08:00"


def test_sanitize_cwa_payload_redacts_nested_authorization_values():
    payload = {
        "Authorization": "real-key",
        "nested": [
            {
                "ProductURL": "https://example.test/file.json?Authorization=CWA-FAKE-KEY"
            }
        ],
    }

    sanitized = sanitize_cwa_payload(payload)

    text = str(sanitized)
    assert sanitized["Authorization"] == "REDACTED"
    assert "Authorization=REDACTED" in text
    assert "real-key" not in text
    assert "CWA-FAKE-KEY" not in text


def test_dry_run_index_has_no_files_and_redacted_source():
    request = CwaHistoryRequest(
        data_id="O-A0059-001",
        base_url="https://example.test/historyapi/v1/getMetadata",
    )

    index = dry_run_index(request)

    assert index.dry_run is True
    assert index.files == ()
    assert "Authorization=REDACTED" in index.source_url


def test_fetch_history_index_parses_response_and_redacts_source_url():
    def fake_get(url: str, *, params: dict[str, str], timeout: int, verify: bool) -> FakeResponse:
        return FakeResponse(
            b'{"files":[{"dataTime":"2026-07-06T19:30:00+08:00","downloadURL":"https://example.test/a.json"}]}',
            url=f"{url}?Authorization={params['Authorization']}",
        )

    request = CwaHistoryRequest(
        data_id="O-A0059-001",
        base_url="https://example.test/historyapi/v1/getMetadata",
    )
    index = fetch_history_index(request, authorization="real-key", http_get=fake_get)

    assert len(index.files) == 1
    assert index.files[0].url == "https://example.test/a.json"
    assert "real-key" not in index.source_url
    assert "Authorization=REDACTED" in index.source_url


def test_fetch_history_index_redacts_request_errors():
    def fake_get(url: str, *, params: dict[str, str], timeout: int, verify: bool) -> FakeResponse:
        raise RuntimeError(f"failed {url}?Authorization={params['Authorization']}")

    request = CwaHistoryRequest(
        data_id="O-A0059-001",
        base_url="https://example.test/historyapi/v1/getMetadata",
    )

    try:
        fetch_history_index(request, authorization="real-key", http_get=fake_get)
    except RuntimeError as exc:
        message = str(exc)
        assert "real-key" not in message
        assert "Authorization=REDACTED" in message
        assert "RuntimeError" in message
    else:
        raise AssertionError("expected history request to fail")
