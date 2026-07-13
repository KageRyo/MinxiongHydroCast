"""Download CWA Open Data file API products without exposing API keys."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings

from minxionghydrocast.config import get_settings
from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "cwa_file_api_download"
DEFAULT_DATA_ID = "O-A0059-001"
DEFAULT_OUTPUT_DIR = Path("data/external/radar")
VALID_DATA_ID = re.compile(r"^[A-Z]-[A-Z][0-9]{4}-[0-9]{3}$")


class HttpResponse(Protocol):
    content: bytes
    status_code: int
    url: str
    headers: dict[str, str]

    def raise_for_status(self) -> None: ...


class HttpGet(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class CwaDownloadRequest:
    data_id: str
    file_format: str = "JSON"
    download_type: str = "WEB"
    base_url: str = ""

    def validate(self) -> None:
        if not VALID_DATA_ID.match(self.data_id):
            raise ValueError(f"invalid CWA data id: {self.data_id}")
        if not self.file_format:
            raise ValueError("file format must not be empty")
        if not self.download_type:
            raise ValueError("download type must not be empty")

    @property
    def endpoint(self) -> str:
        base_url = self.base_url or get_settings().cwa_open_data_file_api_url
        return f"{base_url.rstrip('/')}/{self.data_id}"

    def params(self, *, authorization: str) -> dict[str, str]:
        return {
            "Authorization": authorization,
            "downloadType": self.download_type,
            "format": self.file_format.upper(),
        }

    def redacted_url(self) -> str:
        return append_query(
            self.endpoint,
            {
                "Authorization": "REDACTED",
                "downloadType": self.download_type,
                "format": self.file_format.upper(),
            },
        )


@dataclass(frozen=True)
class DownloadResult:
    data_id: str
    output_path: Path
    bytes_written: int
    redacted_url: str
    dry_run: bool = False


def append_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def redact_authorization_url(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        query.append((key, "REDACTED" if key == "Authorization" else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def output_path_for_request(
    request: CwaDownloadRequest,
    *,
    output_dir: Path,
    output: Path | None = None,
) -> Path:
    if output is not None:
        return output
    extension = request.file_format.lower()
    source_dir = f"cwa_{request.data_id.lower().replace('-', '_')}"
    return output_dir / source_dir / f"{request.data_id}.{extension}"


def looks_like_cwa_auth_error(payload: bytes) -> bool:
    text = payload[:500].decode("utf-8", errors="ignore")
    return (
        "Authorization key is not correct" in text
        or "Authorization" in text
        and "Forbidden" in text
    )


def download_cwa_file(
    request: CwaDownloadRequest,
    *,
    authorization: str,
    output_path: Path,
    timeout: int = 60,
    http_get: HttpGet = requests.get,
    overwrite: bool = False,
    verify_tls: bool = True,
) -> DownloadResult:
    request.validate()
    if not authorization:
        raise ValueError("missing CWA API key")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output_path}")

    if not verify_tls:
        disable_warnings(InsecureRequestWarning)

    try:
        response = http_get(
            request.endpoint,
            params=request.params(authorization=authorization),
            timeout=timeout,
            verify=verify_tls,
        )
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"CWA request failed for {request.redacted_url()}: {type(exc).__name__}"
        ) from exc
    if looks_like_cwa_auth_error(response.content):
        raise RuntimeError("CWA rejected the Authorization key")
    if not response.content:
        raise RuntimeError("CWA returned an empty response")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return DownloadResult(
        data_id=request.data_id,
        output_path=output_path,
        bytes_written=len(response.content),
        redacted_url=redact_authorization_url(response.url),
    )


def dry_run_result(request: CwaDownloadRequest, output_path: Path) -> DownloadResult:
    request.validate()
    return DownloadResult(
        data_id=request.data_id,
        output_path=output_path,
        bytes_written=0,
        redacted_url=request.redacted_url(),
        dry_run=True,
    )


def build_download_summary(
    *,
    status: str,
    failure_reason: str,
    result: DownloadResult | None,
    request: CwaDownloadRequest,
    output_path: Path,
    started_at: str,
    start_timer: float,
    api_key_env: str,
    key_present: bool,
    timeout: int,
    overwrite: bool,
    verify_tls: bool,
) -> dict[str, object]:
    return build_run_summary(
        pipeline=PIPELINE_NAME,
        status=status,
        failure_reason=failure_reason,
        started_at=started_at,
        start_timer=start_timer,
        inputs={"data_id": request.data_id, "format": request.file_format.upper()},
        outputs={"download": str(output_path)},
        row_counts={"bytes": result.bytes_written if result else 0},
        metadata={
            "download_type": request.download_type,
            "dry_run": result.dry_run if result else False,
            "redacted_url": result.redacted_url if result else request.redacted_url(),
            "api_key_env": api_key_env,
            "api_key_present": key_present,
            "timeout_seconds": timeout,
            "overwrite": overwrite,
            "verify_tls": verify_tls,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a CWA Open Data file API product.")
    parser.add_argument("--data-id", default=DEFAULT_DATA_ID)
    parser.add_argument("--format", default="JSON", dest="file_format")
    parser.add_argument("--download-type", default="WEB")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification for local CWA sampling only.",
    )
    parser.add_argument("--api-key-env", default="CWA_API_KEY")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    request = CwaDownloadRequest(
        data_id=args.data_id,
        file_format=args.file_format,
        download_type=args.download_type,
    )
    output_path = output_path_for_request(request, output_dir=args.output_dir, output=args.output)
    started_at, start_timer = start_run()
    authorization = os.getenv(args.api_key_env, "")

    try:
        if args.dry_run:
            result = dry_run_result(request, output_path)
        else:
            result = download_cwa_file(
                request,
                authorization=authorization,
                output_path=output_path,
                timeout=args.timeout,
                overwrite=args.overwrite,
                verify_tls=not args.insecure_tls,
            )
        summary = build_download_summary(
            status="ok",
            failure_reason="",
            result=result,
            request=request,
            output_path=output_path,
            started_at=started_at,
            start_timer=start_timer,
            api_key_env=args.api_key_env,
            key_present=bool(authorization),
            timeout=args.timeout,
            overwrite=args.overwrite,
            verify_tls=not args.insecure_tls,
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        action = "Dry run for" if args.dry_run else "Downloaded"
        print(f"[OK] {action} {request.data_id} -> {output_path}")
    except Exception as exc:
        summary = build_download_summary(
            status="error",
            failure_reason=str(exc),
            result=None,
            request=request,
            output_path=output_path,
            started_at=started_at,
            start_timer=start_timer,
            api_key_env=args.api_key_env,
            key_present=bool(authorization),
            timeout=args.timeout,
            overwrite=args.overwrite,
            verify_tls=not args.insecure_tls,
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        raise SystemExit(f"[ERROR] {exc}") from exc


if __name__ == "__main__":
    main()
