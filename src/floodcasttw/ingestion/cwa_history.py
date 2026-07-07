"""List CWA short-term history files without exposing API keys."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from floodcasttw.config import get_settings
from floodcasttw.ingestion.cwa_file_api import VALID_DATA_ID
from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "cwa_history_list"
DEFAULT_DATA_ID = "O-A0059-001"
DEFAULT_OUTPUT = Path("data/processed/cwa_history_index.json")

TIME_KEYS = ("dataTime", "DataTime", "datetime", "DateTime", "time", "Time", "validTime")
URL_KEYS = ("url", "URL", "downloadURL", "downloadUrl", "fileURL", "fileUrl", "filePath")
NAME_KEYS = ("filename", "fileName", "name", "Name", "resourceName")
FORMAT_KEYS = ("format", "Format", "fileFormat")
SIZE_KEYS = ("size", "fileSize", "FileSize")


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
class CwaHistoryRequest:
    data_id: str
    base_url: str = ""

    def validate(self) -> None:
        if not VALID_DATA_ID.match(self.data_id):
            raise ValueError(f"invalid CWA data id: {self.data_id}")

    @property
    def endpoint(self) -> str:
        base_url = self.base_url or get_settings().cwa_history_api_url
        return f"{base_url.rstrip('/')}/{self.data_id}"

    def params(self, *, authorization: str) -> dict[str, str]:
        return {"Authorization": authorization}

    def redacted_url(self) -> str:
        return append_query(self.endpoint, {"Authorization": "REDACTED"})


@dataclass(frozen=True)
class CwaHistoryFile:
    data_time: str
    url: str
    filename: str
    file_format: str
    size: str
    raw: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "data_time": self.data_time,
            "url": self.url,
            "filename": self.filename,
            "file_format": self.file_format,
            "size": self.size,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class CwaHistoryIndex:
    data_id: str
    source_url: str
    files: tuple[CwaHistoryFile, ...]
    raw: dict[str, object]
    dry_run: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "data_id": self.data_id,
            "source_url": self.source_url,
            "dry_run": self.dry_run,
            "file_count": len(self.files),
            "files": [file.to_dict() for file in self.files],
            "raw": self.raw,
        }


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


def _first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _iter_dicts(payload: Any) -> list[dict[str, Any]]:
    found = []
    if isinstance(payload, dict):
        found.append(payload)
        for value in payload.values():
            found.extend(_iter_dicts(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_iter_dicts(item))
    return found


def extract_history_files(payload: dict[str, Any]) -> tuple[CwaHistoryFile, ...]:
    files = []
    for item in _iter_dicts(payload):
        url = _first_string(item, URL_KEYS)
        filename = _first_string(item, NAME_KEYS)
        data_time = _first_string(item, TIME_KEYS)
        if not any((url, filename, data_time)):
            continue
        files.append(
            CwaHistoryFile(
                data_time=data_time,
                url=url,
                filename=filename,
                file_format=_first_string(item, FORMAT_KEYS),
                size=_first_string(item, SIZE_KEYS),
                raw={str(key): value for key, value in item.items()},
            )
        )
    return tuple(files)


def fetch_history_index(
    request: CwaHistoryRequest,
    *,
    authorization: str,
    timeout: int = 60,
    http_get: HttpGet = requests.get,
    verify_tls: bool = True,
) -> CwaHistoryIndex:
    request.validate()
    if not authorization:
        raise ValueError("missing CWA API key")
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
        payload = json.loads(response.content.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"CWA history request failed for {request.redacted_url()}: {type(exc).__name__}"
        ) from exc

    files = extract_history_files(payload)
    return CwaHistoryIndex(
        data_id=request.data_id,
        source_url=redact_authorization_url(response.url),
        files=files,
        raw=payload,
    )


def dry_run_index(request: CwaHistoryRequest) -> CwaHistoryIndex:
    request.validate()
    return CwaHistoryIndex(
        data_id=request.data_id,
        source_url=request.redacted_url(),
        files=(),
        raw={},
        dry_run=True,
    )


def write_history_index(path: Path, index: CwaHistoryIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_history_summary(
    *,
    status: str,
    failure_reason: str,
    request: CwaHistoryRequest,
    index: CwaHistoryIndex | None,
    output: Path,
    started_at: str,
    start_timer: float,
    api_key_env: str,
    key_present: bool,
    timeout: int,
    verify_tls: bool,
) -> dict[str, object]:
    return build_run_summary(
        pipeline=PIPELINE_NAME,
        status=status,
        failure_reason=failure_reason,
        started_at=started_at,
        start_timer=start_timer,
        inputs={"data_id": request.data_id},
        outputs={"history_index": str(output)},
        row_counts={"files": len(index.files) if index else 0},
        metadata={
            "redacted_url": index.source_url if index else request.redacted_url(),
            "dry_run": index.dry_run if index else False,
            "api_key_env": api_key_env,
            "api_key_present": key_present,
            "timeout_seconds": timeout,
            "verify_tls": verify_tls,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="List CWA short-term history files.")
    parser.add_argument("--data-id", default=DEFAULT_DATA_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=60)
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

    request = CwaHistoryRequest(data_id=args.data_id)
    authorization = os.getenv(args.api_key_env, "")
    started_at, start_timer = start_run()
    try:
        if args.dry_run:
            index = dry_run_index(request)
        else:
            index = fetch_history_index(
                request,
                authorization=authorization,
                timeout=args.timeout,
                verify_tls=not args.insecure_tls,
            )
        write_history_index(args.output, index)
        summary = build_history_summary(
            status="ok",
            failure_reason="",
            request=request,
            index=index,
            output=args.output,
            started_at=started_at,
            start_timer=start_timer,
            api_key_env=args.api_key_env,
            key_present=bool(authorization),
            timeout=args.timeout,
            verify_tls=not args.insecure_tls,
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        print(f"[OK] Wrote CWA history index to {args.output}")
    except Exception as exc:
        summary = build_history_summary(
            status="error",
            failure_reason=str(exc),
            request=request,
            index=None,
            output=args.output,
            started_at=started_at,
            start_timer=start_timer,
            api_key_env=args.api_key_env,
            key_present=bool(authorization),
            timeout=args.timeout,
            verify_tls=not args.insecure_tls,
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        raise SystemExit(f"[ERROR] {exc}") from exc


if __name__ == "__main__":
    main()
