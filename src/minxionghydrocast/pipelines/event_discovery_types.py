"""Shared protocols and result types for radar event discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from minxionghydrocast.ingestion.cwa_event_collector import (
    HttpResponse as FrameHttpResponse,
)
from minxionghydrocast.ingestion.cwa_file_api import HttpResponse as FileHttpResponse
from minxionghydrocast.ingestion.cwa_history import HttpResponse as HistoryHttpResponse


class HistoryHttpGet(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> HistoryHttpResponse: ...


class FrameHttpGet(Protocol):
    def __call__(self, url: str, *, timeout: int, verify: bool) -> FrameHttpResponse: ...


class FileHttpGet(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> FileHttpResponse: ...


@dataclass(frozen=True)
class EventDiscoveryResult:
    catalog_path: Path
    catalog_changed: bool
    scanned_frame_count: int
    context_trigger_frame_count: int
    trigger_frame_count: int
    candidate_count: int
    complete_candidate_count: int
    evidence_error_count: int
    cache_files_removed: int
    cache_bytes_removed: int
