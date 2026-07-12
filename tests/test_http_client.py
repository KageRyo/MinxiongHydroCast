import json

import pytest

from floodcastminxiong.ingestion.http_client import (
    ReliableJsonClient,
    RetryPolicy,
    close_verified_session,
    _verified_session,
    verified_compatible_ssl_context,
)
from floodcastminxiong.ingestion.source_adapter import SourceRequestError, SourceSchemaError


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.url = "https://example.test/data?Authorization=secret"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_compatible_tls_context_keeps_certificate_and_hostname_verification():
    context = verified_compatible_ssl_context()

    assert context.verify_mode.name == "CERT_REQUIRED"
    assert context.check_hostname is True


def test_close_verified_session_does_not_create_an_unused_session():
    close_verified_session()

    assert _verified_session.cache_info().currsize == 0


def test_reliable_client_retries_with_exponential_backoff():
    responses = [FakeResponse(b"busy", 503), FakeResponse(b'{"ok": true}')]
    sleeps: list[float] = []

    def fake_get(
        _url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None,
        timeout: float,
    ):
        assert params == {"Authorization": "secret"}
        assert headers is None
        assert timeout == 10
        return responses.pop(0)

    client = ReliableJsonClient(
        http_get=fake_get,
        retry_policy=RetryPolicy(attempts=3, backoff_seconds=0.5),
        minimum_interval_seconds=0,
        sleep=sleeps.append,
    )

    response = client.get_json(
        "https://example.test/data",
        params={"Authorization": "secret"},
        timeout_seconds=10,
        redacted_url="https://example.test/data?Authorization=REDACTED",
    )

    assert response.payload == {"ok": True}
    assert sleeps == [0.5]


def test_reliable_client_classifies_rate_limit_without_leaking_key():
    def fake_get(
        _url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None,
        timeout: float,
    ):
        assert headers is None
        return FakeResponse(b"busy", 429)

    client = ReliableJsonClient(
        http_get=fake_get,
        retry_policy=RetryPolicy(attempts=2, backoff_seconds=0),
        minimum_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(SourceRequestError) as exc_info:
        client.get_json(
            "https://example.test/data",
            params={"Authorization": "real-secret"},
            timeout_seconds=10,
            redacted_url="https://example.test/data?Authorization=REDACTED",
        )

    assert exc_info.value.kind == "rate_limited"
    assert "real-secret" not in str(exc_info.value)


def test_reliable_client_enforces_minimum_request_interval():
    sleeps: list[float] = []
    client = ReliableJsonClient(
        http_get=lambda _url, **_kwargs: FakeResponse(b'{"ok": true}'),
        minimum_interval_seconds=0.2,
        sleep=sleeps.append,
        monotonic=lambda: 10.0,
    )
    request = {
        "url": "https://example.test/data",
        "params": {},
        "timeout_seconds": 10,
        "redacted_url": "https://example.test/data",
    }

    client.get_json(**request)
    client.get_json(**request)

    assert sleeps == [0.2]


@pytest.mark.parametrize("content", [b"", b"not-json", json.dumps([1, 2]).encode()])
def test_reliable_client_rejects_invalid_json_contract(content: bytes):
    client = ReliableJsonClient(
        http_get=lambda _url, **_kwargs: FakeResponse(content),
        minimum_interval_seconds=0,
    )

    with pytest.raises(SourceSchemaError) as exc_info:
        client.get_json(
            "https://example.test/data",
            params={},
            timeout_seconds=10,
            redacted_url="https://example.test/data",
        )

    assert exc_info.value.kind == "schema_drift"


def test_reliable_client_passes_secret_header_without_adding_it_to_errors():
    def fake_get(
        _url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None,
        timeout: float,
    ):
        assert params == {}
        assert headers == {"apikey": "real-secret"}
        assert timeout == 10
        return FakeResponse(b"busy", 503)

    client = ReliableJsonClient(
        http_get=fake_get,
        retry_policy=RetryPolicy(attempts=1),
        minimum_interval_seconds=0,
    )

    with pytest.raises(SourceRequestError) as exc_info:
        client.get_json(
            "https://example.test/data",
            params={},
            headers={"apikey": "real-secret"},
            timeout_seconds=10,
            redacted_url="https://example.test/data",
        )

    assert "real-secret" not in str(exc_info.value)


def test_reliable_client_accepts_array_root_when_requested():
    client = ReliableJsonClient(
        http_get=lambda _url, **_kwargs: FakeResponse(b'[{"ok": true}]'),
        minimum_interval_seconds=0,
    )

    response = client.get_json(
        "https://example.test/data",
        params={},
        timeout_seconds=10,
        redacted_url="https://example.test/data",
        expected_root="array",
    )

    assert response.payload == [{"ok": True}]
