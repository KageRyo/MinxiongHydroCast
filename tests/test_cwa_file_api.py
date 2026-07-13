from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from minxionghydrocast.ingestion.cwa_file_api import (
    CwaDownloadRequest,
    download_cwa_file,
    dry_run_result,
    output_path_for_request,
    redact_authorization_url,
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


def test_cwa_download_request_builds_official_query_params():
    request = CwaDownloadRequest(
        data_id="O-A0059-001",
        file_format="json",
        base_url="https://example.test/fileapi/v1/opendataapi",
    )

    assert request.endpoint == "https://example.test/fileapi/v1/opendataapi/O-A0059-001"
    assert request.params(authorization="abc") == {
        "Authorization": "abc",
        "downloadType": "WEB",
        "format": "JSON",
    }


def test_redact_authorization_url_keeps_other_query_params():
    redacted = redact_authorization_url(
        "https://example.test/O-A0059-001?Authorization=real-key&downloadType=WEB&format=JSON"
    )
    query = parse_qs(urlsplit(redacted).query)

    assert query["Authorization"] == ["REDACTED"]
    assert query["downloadType"] == ["WEB"]
    assert query["format"] == ["JSON"]
    assert "real-key" not in redacted


def test_output_path_defaults_to_data_id_directory(tmp_path: Path):
    request = CwaDownloadRequest(data_id="O-B0045-001", file_format="XML")

    assert output_path_for_request(request, output_dir=tmp_path) == (
        tmp_path / "cwa_o_b0045_001" / "O-B0045-001.xml"
    )


def test_dry_run_returns_redacted_url_without_writing_file(tmp_path: Path):
    request = CwaDownloadRequest(
        data_id="O-A0059-001",
        base_url="https://example.test/fileapi/v1/opendataapi",
    )
    output = tmp_path / "sample.json"

    result = dry_run_result(request, output)

    assert result.dry_run is True
    assert result.output_path == output
    assert result.bytes_written == 0
    assert "Authorization=REDACTED" in result.redacted_url
    assert not output.exists()


def test_download_cwa_file_writes_response_and_redacts_url(tmp_path: Path):
    calls = []

    def fake_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> FakeResponse:
        calls.append((url, params, timeout, verify))
        return FakeResponse(
            b'{"success": true}',
            url=f"{url}?Authorization={params['Authorization']}&downloadType=WEB&format=JSON",
        )

    request = CwaDownloadRequest(
        data_id="O-A0059-001",
        base_url="https://example.test/fileapi/v1/opendataapi",
    )
    output = tmp_path / "download.json"

    result = download_cwa_file(
        request,
        authorization="real-key",
        output_path=output,
        http_get=fake_get,
    )

    assert output.read_bytes() == b'{"success": true}'
    assert result.bytes_written == 17
    assert "real-key" not in result.redacted_url
    assert calls == [
        (
            "https://example.test/fileapi/v1/opendataapi/O-A0059-001",
            {"Authorization": "real-key", "downloadType": "WEB", "format": "JSON"},
            60,
            True,
        )
    ]


def test_download_cwa_file_retries_and_writes_atomically(tmp_path: Path):
    calls = 0

    def flaky_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure")
        return FakeResponse(b'{"complete": true}', url=url)

    output = tmp_path / "download.json"
    result = download_cwa_file(
        CwaDownloadRequest(data_id="O-B0045-001"),
        authorization="real-key",
        output_path=output,
        http_get=flaky_get,
        retry_attempts=2,
        retry_backoff_seconds=0,
    )

    assert calls == 2
    assert result.bytes_written == len(b'{"complete": true}')
    assert output.read_bytes() == b'{"complete": true}'
    assert list(tmp_path.glob(".*.tmp")) == []


def test_download_requires_local_authorization_key(tmp_path: Path):
    request = CwaDownloadRequest(data_id="O-A0059-001")

    try:
        download_cwa_file(request, authorization="", output_path=tmp_path / "sample.json")
    except ValueError as exc:
        assert "missing CWA API key" in str(exc)
    else:
        raise AssertionError("expected missing key to fail")


def test_download_does_not_overwrite_without_flag(tmp_path: Path):
    request = CwaDownloadRequest(data_id="O-A0059-001")
    output = tmp_path / "sample.json"
    output.write_text("existing", encoding="utf-8")

    try:
        download_cwa_file(request, authorization="key", output_path=output)
    except FileExistsError as exc:
        assert "output already exists" in str(exc)
    else:
        raise AssertionError("expected existing output to fail")


def test_download_redacts_authorization_from_request_errors(tmp_path: Path):
    def fake_get(
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> FakeResponse:
        raise RuntimeError(
            f"failed URL {url}?Authorization={params['Authorization']}&format=JSON"
        )

    request = CwaDownloadRequest(
        data_id="O-A0059-001",
        base_url="https://example.test/fileapi/v1/opendataapi",
    )

    try:
        download_cwa_file(
            request,
            authorization="real-key",
            output_path=tmp_path / "sample.json",
            http_get=fake_get,
            verify_tls=False,
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "real-key" not in message
        assert "Authorization=REDACTED" in message
        assert "RuntimeError" in message
    else:
        raise AssertionError("expected request error to fail")
