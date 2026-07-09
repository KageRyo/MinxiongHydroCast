"""Download timestamped CWA history data products without exposing API keys."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from floodcasttw.config import get_settings
from floodcasttw.ingestion.cwa_file_api import VALID_DATA_ID, looks_like_cwa_auth_error
from floodcasttw.ingestion.cwa_history import append_query, redact_authorization_url
from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "cwa_history_data_download"
DEFAULT_DATA_ID = "O-A0002-001"
DEFAULT_OUTPUT_DIR = Path("data/external/cwa_history")


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
class CwaHistoryDataRequest:
    data_id: str
    data_time: str
    base_url: str = ""

    def validate(self) -> None:
        if not VALID_DATA_ID.match(self.data_id):
            raise ValueError(f"invalid CWA data id: {self.data_id}")
        parse_iso_datetime(self.data_time)

    @property
    def endpoint(self) -> str:
        parsed = parse_iso_datetime(self.data_time)
        base_url = self.base_url or get_settings().cwa_history_data_api_url
        return (
            f"{base_url.rstrip('/')}/{self.data_id}/"
            f"{parsed:%Y}/{parsed:%m}/{parsed:%d}/{parsed:%H}/{parsed:%M}/{parsed:%S}"
        )

    def params(self, *, authorization: str) -> dict[str, str]:
        return {"Authorization": authorization}

    def redacted_url(self) -> str:
        return append_query(self.endpoint, {"Authorization": "REDACTED"})


@dataclass(frozen=True)
class CwaHistoryDataResult:
    data_id: str
    data_time: str
    output_path: Path
    bytes_written: int
    redacted_url: str
    content_type: str
    dry_run: bool = False


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def output_path_for_request(
    request: CwaHistoryDataRequest,
    *,
    output_dir: Path,
    output: Path | None = None,
) -> Path:
    if output is not None:
        return output
    parsed = parse_iso_datetime(request.data_time)
    source_dir = f"cwa_{request.data_id.lower().replace('-', '_')}"
    return output_dir / source_dir / f"{request.data_id}_{parsed:%Y%m%d%H%M%S}.dat"


def download_history_data(
    request: CwaHistoryDataRequest,
    *,
    authorization: str,
    output_path: Path,
    timeout: int = 60,
    http_get: HttpGet = requests.get,
    overwrite: bool = False,
    verify_tls: bool = True,
) -> CwaHistoryDataResult:
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
        status_code = getattr(locals().get("response", None), "status_code", None)
        status_detail = f" HTTP {status_code}" if status_code is not None else ""
        raise RuntimeError(
            "CWA history data request failed for "
            f"{request.redacted_url()}: {type(exc).__name__}{status_detail}"
        ) from exc
    if looks_like_cwa_auth_error(response.content):
        raise RuntimeError("CWA rejected the Authorization key")
    if not response.content:
        raise RuntimeError(f"CWA returned an empty history data file for {request.redacted_url()}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return CwaHistoryDataResult(
        data_id=request.data_id,
        data_time=request.data_time,
        output_path=output_path,
        bytes_written=len(response.content),
        redacted_url=redact_authorization_url(response.url),
        content_type=response.headers.get("content-type", ""),
    )


def dry_run_result(
    request: CwaHistoryDataRequest,
    *,
    output_path: Path,
) -> CwaHistoryDataResult:
    request.validate()
    return CwaHistoryDataResult(
        data_id=request.data_id,
        data_time=request.data_time,
        output_path=output_path,
        bytes_written=0,
        redacted_url=request.redacted_url(),
        content_type="",
        dry_run=True,
    )


def build_history_data_summary(
    *,
    status: str,
    failure_reason: str,
    result: CwaHistoryDataResult | None,
    request: CwaHistoryDataRequest,
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
        inputs={"data_id": request.data_id, "data_time": request.data_time},
        outputs={"download": str(output_path)},
        row_counts={"bytes": result.bytes_written if result else 0},
        metadata={
            "dry_run": result.dry_run if result else False,
            "redacted_url": result.redacted_url if result else request.redacted_url(),
            "content_type": result.content_type if result else "",
            "api_key_env": api_key_env,
            "api_key_present": key_present,
            "timeout_seconds": timeout,
            "overwrite": overwrite,
            "verify_tls": verify_tls,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a timestamped CWA history data file.")
    parser.add_argument("--data-id", default=DEFAULT_DATA_ID)
    parser.add_argument("--data-time", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api-key-env", default="CWA_API_KEY")
    parser.add_argument(
        "--insecure-tls",
        action="store_true",
        help="Disable TLS certificate verification for local CWA sampling only.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    request = CwaHistoryDataRequest(data_id=args.data_id, data_time=args.data_time)
    output_path = output_path_for_request(request, output_dir=args.output_dir, output=args.output)
    authorization = os.getenv(args.api_key_env, "")
    started_at, start_timer = start_run()
    try:
        if args.dry_run:
            result = dry_run_result(request, output_path=output_path)
        else:
            result = download_history_data(
                request,
                authorization=authorization,
                output_path=output_path,
                timeout=args.timeout,
                overwrite=args.overwrite,
                verify_tls=not args.insecure_tls,
            )
        summary = build_history_data_summary(
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
        print(f"[OK] Wrote CWA history data to {output_path}")
    except Exception as exc:
        summary = build_history_data_summary(
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
