from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from minxionghydrocast.ingestion.cwa_history_data import (
    CwaHistoryDataRequest,
    download_history_data,
    dry_run_result,
    output_path_for_request,
)


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        url: str,
        status_code: int = 200,
        content_type: str = "application/xml",
    ):
        self.content = content
        self.url = url
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_history_data_request_builds_timestamped_redacted_url():
    request = CwaHistoryDataRequest(
        data_id="O-A0002-001",
        data_time="2026-07-02T15:30:00+08:00",
        base_url="https://example.test/historyapi/v1/getData",
    )
    query = parse_qs(urlsplit(request.redacted_url()).query)

    assert (
        request.endpoint
        == "https://example.test/historyapi/v1/getData/O-A0002-001/2026/07/02/15/30/00"
    )
    assert request.params(authorization="real-key") == {"Authorization": "real-key"}
    assert query["Authorization"] == ["REDACTED"]


def test_output_path_for_request_uses_data_id_and_timestamp():
    request = CwaHistoryDataRequest(
        data_id="O-A0002-001",
        data_time="2026-07-02T15:30:00+08:00",
    )

    output_path = output_path_for_request(request, output_dir=Path("data/external/cwa_history"))

    assert output_path == Path(
        "data/external/cwa_history/cwa_o_a0002_001/O-A0002-001_20260702153000.dat"
    )


def test_dry_run_result_has_redacted_url(tmp_path: Path):
    request = CwaHistoryDataRequest(
        data_id="O-A0002-001",
        data_time="2026-07-02T15:30:00+08:00",
        base_url="https://example.test/historyapi/v1/getData",
    )

    result = dry_run_result(request, output_path=tmp_path / "gauge.xml")

    assert result.dry_run is True
    assert result.bytes_written == 0
    assert "Authorization=REDACTED" in result.redacted_url


def test_download_history_data_writes_bytes_and_redacts_result_url(tmp_path: Path):
    requested = []

    def fake_get(url: str, *, params: dict[str, str], timeout: int, verify: bool) -> FakeResponse:
        requested.append((url, params, timeout, verify))
        return FakeResponse(
            b"<?xml version='1.0'?><cwaopendata />",
            f"{url}?Authorization={params['Authorization']}",
        )

    request = CwaHistoryDataRequest(
        data_id="O-A0002-001",
        data_time="2026-07-02T15:30:00+08:00",
        base_url="https://example.test/historyapi/v1/getData",
    )
    output = tmp_path / "gauge.xml"

    result = download_history_data(
        request,
        authorization="real-key",
        output_path=output,
        http_get=fake_get,
    )

    assert output.read_bytes() == b"<?xml version='1.0'?><cwaopendata />"
    assert result.bytes_written == len(b"<?xml version='1.0'?><cwaopendata />")
    assert result.content_type == "application/xml"
    assert "real-key" not in result.redacted_url
    assert "Authorization=REDACTED" in result.redacted_url
    assert requested[0][1] == {"Authorization": "real-key"}


def test_download_history_data_redacts_request_errors(tmp_path: Path):
    def fake_get(url: str, *, params: dict[str, str], timeout: int, verify: bool) -> FakeResponse:
        raise RuntimeError(f"failed {url}?Authorization={params['Authorization']}")

    request = CwaHistoryDataRequest(
        data_id="O-A0002-001",
        data_time="2026-07-02T15:30:00+08:00",
        base_url="https://example.test/historyapi/v1/getData",
    )

    try:
        download_history_data(
            request,
            authorization="real-key",
            output_path=tmp_path / "gauge.xml",
            http_get=fake_get,
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "real-key" not in message
        assert "Authorization=REDACTED" in message
        assert "RuntimeError" in message
    else:
        raise AssertionError("expected history data request to fail")
