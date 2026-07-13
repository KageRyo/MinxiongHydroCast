"""Small reliable HTTP JSON client for official source adapters."""

from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Literal, Protocol

import requests
from requests.adapters import HTTPAdapter

from minxionghydrocast.ingestion.source_adapter import (
    SourceRequestError,
    SourceSchemaError,
)


class HttpResponse(Protocol):
    content: bytes
    status_code: int
    url: str

    def raise_for_status(self) -> None: ...


class HttpGet(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None,
        timeout: float,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class JsonResponse:
    payload: dict[str, Any] | list[Any]
    content: bytes
    url: str


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_seconds: float = 0.5
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("retry attempts must be at least one")
        if self.backoff_seconds < 0:
            raise ValueError("retry backoff must not be negative")


def verified_compatible_ssl_context() -> ssl.SSLContext:
    """Keep CA/hostname checks while tolerating legacy chains without strict SKI metadata."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        context.verify_flags &= ~strict_flag
    return context


class VerifiedCompatibleTlsAdapter(HTTPAdapter):
    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: Any,
    ) -> None:
        pool_kwargs["ssl_context"] = verified_compatible_ssl_context()
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


@lru_cache(maxsize=1)
def _verified_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", VerifiedCompatibleTlsAdapter())
    return session


def close_verified_session() -> None:
    """Close the shared transport pool without creating it when it was unused."""

    if _verified_session.cache_info().currsize:
        _verified_session().close()
        _verified_session.cache_clear()


def verified_get(
    url: str,
    *,
    params: dict[str, str],
    headers: dict[str, str] | None,
    timeout: float,
) -> HttpResponse:
    # Collection runs are sparse; closing each socket avoids retaining cross-host TLS pools.
    request_headers = {**(headers or {}), "Connection": "close"}
    return _verified_session().get(
        url,
        params=params,
        headers=request_headers,
        timeout=timeout,
    )


class ReliableJsonClient:
    def __init__(
        self,
        *,
        http_get: HttpGet = verified_get,
        retry_policy: RetryPolicy | None = None,
        minimum_interval_seconds: float = 0.2,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum request interval must not be negative")
        self._http_get = http_get
        self._retry_policy = retry_policy or RetryPolicy()
        self._minimum_interval_seconds = minimum_interval_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def _rate_limit(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._minimum_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_at = now

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
        timeout_seconds: float,
        redacted_url: str,
        expected_root: Literal["object", "array"] = "object",
    ) -> JsonResponse:
        if timeout_seconds <= 0:
            raise ValueError("HTTP timeout must be positive")

        last_error_kind = "transport"
        for attempt in range(1, self._retry_policy.attempts + 1):
            self._rate_limit()
            try:
                response = self._http_get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout_seconds,
                )
                status_code = int(response.status_code)
                if status_code in self._retry_policy.retry_statuses:
                    last_error_kind = "rate_limited" if status_code == 429 else "http"
                    raise RuntimeError(f"retryable HTTP {status_code}")
                if status_code in {401, 403}:
                    raise SourceRequestError(
                        "authentication",
                        f"official source rejected credentials: {redacted_url}",
                    )
                response.raise_for_status()
            except SourceRequestError:
                raise
            except Exception as exc:
                if attempt == self._retry_policy.attempts:
                    raise SourceRequestError(
                        last_error_kind,
                        f"official source request failed after {attempt} attempts: "
                        f"{redacted_url} ({type(exc).__name__})",
                    ) from exc
                self._sleep(self._retry_policy.backoff_seconds * (2 ** (attempt - 1)))
                continue

            if not response.content:
                raise SourceSchemaError(
                    "schema_drift",
                    f"official source returned an empty body: {redacted_url}",
                )
            try:
                payload = json.loads(response.content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SourceSchemaError(
                    "schema_drift",
                    f"official source returned invalid JSON: {redacted_url}",
                ) from exc
            expected_type = dict if expected_root == "object" else list
            if not isinstance(payload, expected_type):
                raise SourceSchemaError(
                    "schema_drift",
                    f"official source JSON root must be an {expected_root}: {redacted_url}",
                )
            return JsonResponse(payload=payload, content=response.content, url=response.url)

        raise AssertionError("retry loop terminated unexpectedly")
