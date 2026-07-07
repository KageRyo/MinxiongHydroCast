"""Build CWA radar event collection plans from history indexes."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from floodcasttw.config import get_settings
from floodcasttw.ingestion.cwa_file_api import looks_like_cwa_auth_error
from floodcasttw.ingestion.cwa_history import redact_authorization_url
from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "cwa_event_plan"
DEFAULT_COLLECTION_OUTPUT = Path("data/processed/cwa_event_collection.json")
DEFAULT_DOWNLOAD_DIR = Path("data/external/radar/events")
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


class HttpResponse(Protocol):
    content: bytes
    status_code: int
    url: str
    headers: dict[str, str]

    def raise_for_status(self) -> None: ...


class UrlGet(Protocol):
    def __call__(self, url: str, *, timeout: int, verify: bool) -> HttpResponse: ...


@dataclass(frozen=True)
class CwaEventFrame:
    data_time: str
    url: str
    filename: str
    file_format: str

    def to_dict(self) -> dict[str, str]:
        return {
            "data_time": self.data_time,
            "url": self.url,
            "filename": self.filename,
            "file_format": self.file_format,
        }


@dataclass(frozen=True)
class CwaEventPlan:
    event_id: str
    data_id: str
    start_time: str
    end_time: str
    frame_count: int
    frames: tuple[CwaEventFrame, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "data_id": self.data_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
        }


@dataclass(frozen=True)
class CwaCollectedFrame:
    data_time: str
    source_url: str
    output_path: str
    bytes_written: int

    def to_dict(self) -> dict[str, object]:
        return {
            "data_time": self.data_time,
            "source_url": self.source_url,
            "output_path": self.output_path,
            "bytes_written": self.bytes_written,
        }


@dataclass(frozen=True)
class CwaEventCollection:
    event_id: str
    data_id: str
    frame_count: int
    bytes_written: int
    frames: tuple[CwaCollectedFrame, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "data_id": self.data_id,
            "frame_count": self.frame_count,
            "bytes_written": self.bytes_written,
            "frames": [frame.to_dict() for frame in self.frames],
        }


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_history_index(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("history index must be a JSON object")
    return payload


def build_event_plan(
    history_index: dict[str, Any],
    *,
    event_id: str,
    start_time: str,
    end_time: str,
    limit: int | None = None,
) -> CwaEventPlan:
    start = parse_iso_datetime(start_time)
    end = parse_iso_datetime(end_time)
    if end < start:
        raise ValueError("end_time must be greater than or equal to start_time")

    frames = []
    for item in history_index.get("files", []):
        if not isinstance(item, dict):
            continue
        data_time = str(item.get("data_time", ""))
        if not data_time:
            continue
        parsed = parse_iso_datetime(data_time)
        if start <= parsed <= end:
            frames.append(
                CwaEventFrame(
                    data_time=data_time,
                    url=redact_authorization_url(str(item.get("url", ""))),
                    filename=str(item.get("filename", "")),
                    file_format=str(item.get("file_format", "")),
                )
            )

    frames.sort(key=lambda frame: parse_iso_datetime(frame.data_time))
    if limit is not None:
        frames = frames[:limit]
    return CwaEventPlan(
        event_id=event_id,
        data_id=str(history_index.get("data_id", "")),
        start_time=start_time,
        end_time=end_time,
        frame_count=len(frames),
        frames=tuple(frames),
    )


def write_event_plan(path: Path, plan: CwaEventPlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def authorize_url(url: str, *, authorization: str) -> str:
    if not authorization:
        raise ValueError("missing CWA API key")
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["Authorization"] = authorization
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_history_data_url(data_id: str, data_time: str) -> str:
    parsed = parse_iso_datetime(data_time)
    base_url = get_settings().cwa_history_data_api_url.rstrip("/")
    return (
        f"{base_url}/{data_id}/"
        f"{parsed:%Y}/{parsed:%m}/{parsed:%d}/{parsed:%H}/{parsed:%M}/{parsed:%S}"
        "?Authorization=REDACTED"
    )


def frame_source_url(frame: CwaEventFrame, *, data_id: str) -> str:
    if frame.url:
        return redact_authorization_url(frame.url)
    return build_history_data_url(data_id, frame.data_time)


def safe_frame_filename(frame: CwaEventFrame, *, data_id: str, index: int) -> str:
    filename = SAFE_NAME.sub("_", frame.filename).strip("._")
    if filename:
        return filename
    parsed = parse_iso_datetime(frame.data_time)
    return f"{data_id}_{parsed:%Y%m%d%H%M%S}_{index:03d}.json"


def download_event_frames(
    plan: CwaEventPlan,
    *,
    output_dir: Path,
    authorization: str,
    timeout: int = 60,
    http_get: UrlGet = requests.get,
    overwrite: bool = False,
    verify_tls: bool = True,
) -> CwaEventCollection:
    if not plan.frames:
        raise ValueError("event plan has no frames")
    if not authorization:
        raise ValueError("missing CWA API key")
    if not verify_tls:
        disable_warnings(InsecureRequestWarning)

    collected: list[CwaCollectedFrame] = []
    event_dir = output_dir / plan.event_id
    for index, frame in enumerate(plan.frames):
        redacted_source_url = frame_source_url(frame, data_id=plan.data_id)
        authorized_url = authorize_url(redacted_source_url, authorization=authorization)
        output_path = event_dir / safe_frame_filename(frame, data_id=plan.data_id, index=index)
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"output already exists: {output_path}")
        try:
            response = http_get(authorized_url, timeout=timeout, verify=verify_tls)
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"CWA frame request failed for {redacted_source_url}: {type(exc).__name__}"
            ) from exc
        if looks_like_cwa_auth_error(response.content):
            raise RuntimeError("CWA rejected the Authorization key")
        if not response.content:
            raise RuntimeError(f"CWA returned an empty frame for {redacted_source_url}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        collected.append(
            CwaCollectedFrame(
                data_time=frame.data_time,
                source_url=redact_authorization_url(response.url),
                output_path=str(output_path),
                bytes_written=len(response.content),
            )
        )

    return CwaEventCollection(
        event_id=plan.event_id,
        data_id=plan.data_id,
        frame_count=len(collected),
        bytes_written=sum(frame.bytes_written for frame in collected),
        frames=tuple(collected),
    )


def write_event_collection(path: Path, collection: CwaEventCollection) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(collection.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a CWA radar event collection plan.")
    parser.add_argument("--history-index", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("data/processed/cwa_event_plan.json"))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--download-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--collection-output", type=Path, default=DEFAULT_COLLECTION_OUTPUT)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--overwrite", action="store_true")
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

    started_at, start_timer = start_run()
    authorization = os.getenv(args.api_key_env, "")
    history_index = load_history_index(args.history_index)
    plan = build_event_plan(
        history_index,
        event_id=args.event_id,
        start_time=args.start_time,
        end_time=args.end_time,
        limit=args.limit,
    )
    write_event_plan(args.output, plan)
    collection = None
    if args.download:
        collection = download_event_frames(
            plan,
            output_dir=args.download_dir,
            authorization=authorization,
            timeout=args.timeout,
            overwrite=args.overwrite,
            verify_tls=not args.insecure_tls,
        )
        write_event_collection(args.collection_output, collection)

    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok" if plan.frames else "needs_review",
        failure_reason="" if plan.frames else "no frames selected",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"history_index": str(args.history_index)},
        outputs={
            "event_plan": str(args.output),
            "collection": str(args.collection_output) if collection else "",
        },
        row_counts={
            "planned_frames": plan.frame_count,
            "downloaded_frames": collection.frame_count if collection else 0,
            "downloaded_bytes": collection.bytes_written if collection else 0,
        },
        metadata={
            "event_id": args.event_id,
            "data_id": plan.data_id,
            "start_time": args.start_time,
            "end_time": args.end_time,
            "limit": args.limit,
            "download": args.download,
            "api_key_env": args.api_key_env,
            "api_key_present": bool(authorization),
            "timeout_seconds": args.timeout,
            "overwrite": args.overwrite,
            "verify_tls": not args.insecure_tls,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote CWA event plan to {args.output}")


if __name__ == "__main__":
    main()
