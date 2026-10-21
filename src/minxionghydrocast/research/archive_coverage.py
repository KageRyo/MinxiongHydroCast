"""Deterministic coverage slots with separate availability, integrity and structural quality."""

from collections import defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from minxionghydrocast.ingestion.cwa_grid import extract_cwa_grid_values
from minxionghydrocast.io.data_store import DataLayout, require_external_data_root, sha256_file
from minxionghydrocast.models.archive_coverage import CoverageEntry, CoverageFrame
from minxionghydrocast.models.radar_tensor import valid_value_mask
from minxionghydrocast.models.rolling_backtest import aware_time
from minxionghydrocast.research.archive_inventory import load_inventory
from minxionghydrocast.research.replay_io import FAILURES, grid_metadata

COUNT_KEYS = ('expected', 'present', 'size_verified', 'checksum_verified', 'usable', 'missing', 'duplicates', 'unchecked')


def _missing(slot: dict) -> bool:
    if slot['state'] == 'uncaptured':
        return True
    artifacts = slot.get('artifacts', [])
    return bool(artifacts) and all(a['state'] == 'file_missing' for a in artifacts)


def _datum(value: str) -> str:
    return {'TWD67經緯網格': 'TWD67', 'EPSG:3821': 'TWD67', 'EPSG:4326': 'WGS84'}.get(value, value)


def _counts(slots: list[dict]) -> dict[str, int]:
    result: dict[str, int] = dict.fromkeys(COUNT_KEYS, 0)
    result['expected'] = len(slots)
    for slot in slots:
        for key in ('present', 'size_verified', 'checksum_verified', 'usable'):
            result[key] += slot[key] is True
        result['missing'] += _missing(slot)
        result['duplicates'] += slot['state'] == 'duplicate_timestamp'
        result['unchecked'] += slot['state'] == 'metadata_invalid' or any(
            artifact['state'] == 'not_checked' for artifact in slot.get('artifacts', [])
        )
    return result


def _intervals(slots: list[dict]) -> list[dict]:
    intervals = []
    current = None
    for slot in slots:
        if not _missing(slot):
            current = None
        elif current is None:
            current = {'start_time': slot['data_time'], 'end_time': slot['data_time'], 'count': 1}
            intervals.append(current)
        else:
            current['end_time'] = slot['data_time']
            current['count'] += 1
    return intervals


def _category(attempt) -> str:
    status = attempt.http_status
    if status in (401, 403) or attempt.failure_kind == 'authentication':
        return 'authentication'
    if status == 429 or attempt.failure_kind == 'rate_limit':
        return 'rate_limit'
    if status == 404:
        return 'http_not_found'
    if attempt.failure_kind in ('transport', 'timeout'):
        return 'transport'
    return 'http_other' if status is not None else 'unknown'


class CoverageReader:
    def __init__(self, layout: DataLayout, budget: int):
        self.layout, self.budget, self.checked = layout, budget, 0

    def structure(self, path: Path, ref: CoverageFrame, entry: CoverageEntry) -> tuple[str, dict | None]:
        try:
            inspection, values = extract_cwa_grid_values(path)
            if inspection.data_id != entry.data_id:
                return 'product_changed', None
            if inspection.units != entry.units:
                return 'units_changed', None
            if aware_time(inspection.data_time).isoformat() != ref.data_time:
                return 'time_mismatch', None
            grid = grid_metadata(inspection)
            if not -90 <= inspection.start_latitude <= 90 or not -180 <= inspection.start_longitude <= 180:
                return 'invalid_grid', None
            if _datum(grid['crs']) != _datum(entry.crs):
                return 'datum_changed', None
            if not valid_value_mask(np.asarray(values), inspection.nodata_values).any():
                return 'all_nodata', grid
            return 'usable', grid
        except FAILURES:
            return 'invalid_source', None

    def artifact(self, ref: CoverageFrame, entry: CoverageEntry) -> dict[str, Any]:
        result: dict[str, Any] = {'state': 'file_missing', 'present': False,
            'size_verified': False, 'checksum_verified': False, 'usable': False,
            'artifact_sha256': ref.sha256}
        try:
            path = self.layout.resolve_relative(ref.path)
        except ValueError:
            result['state'] = 'path_escape'
            return result
        try:
            if not path.is_file():
                return result
            result['present'] = True
            if self.checked >= self.budget:
                result['state'] = 'not_checked'
                return result
            self.checked += 1
            if path.stat().st_size != ref.bytes:
                result['state'] = 'byte_mismatch'
                return result
            result['size_verified'] = True
            if ref.sha256 is None:
                result['state'] = 'checksum_missing'
                return result
            if sha256_file(path) != ref.sha256:
                result['state'] = 'checksum_mismatch'
                return result
            result['checksum_verified'] = True
            result['state'], grid = self.structure(path, ref, entry)
            if grid is not None:
                result['grid'] = grid
            result['usable'] = result['state'] == 'usable'
            return result
        except OSError:
            result['state'] = 'read_error'
            return result

    def slot(self, time: str, refs: list[CoverageFrame], entry: CoverageEntry,
             metadata: str, baseline: dict | None) -> tuple[dict, dict | None]:
        slot: dict[str, Any] = {'data_time': time, 'state': 'uncaptured', 'present': False,
                              'size_verified': False, 'checksum_verified': False, 'usable': False}
        if metadata == 'invalid':
            slot.update(state='metadata_invalid', present=None)
            return slot, baseline
        if not refs:
            return slot, baseline
        checked = [self.artifact(ref, entry) for ref in refs]
        slot['artifacts'] = checked
        for flag in ('present', 'size_verified', 'checksum_verified'):
            slot[flag] = any(item[flag] for item in checked)
        slot['state'] = 'duplicate_timestamp' if len(refs) > 1 else checked[0]['state']
        slot['usable'] = len(refs) == 1 and checked[0]['usable']
        if slot['usable']:
            grid = checked[0]['grid']
            if baseline is not None and grid != baseline:
                slot.update(state='grid_changed', usable=False)
            else:
                baseline = grid
        return slot, baseline

    def entry(self, entry: CoverageEntry, metadata: str, zone: ZoneInfo) -> dict:
        by_time: dict[str, list[CoverageFrame]] = defaultdict(list)
        for ref in entry.frames:
            by_time[ref.data_time].append(ref)
        baseline = None
        slots = []
        for time in entry.times():
            slot, baseline = self.slot(time, by_time.pop(time, []), entry, metadata, baseline)
            slots.append(slot)
        days: dict[str, list[dict]] = defaultdict(list)
        for slot in slots:
            day = aware_time(slot['data_time']).astimezone(zone).date().isoformat()
            days[day].append(slot)
        attempts = [{'record_index': i, 'data_id': a.data_id or entry.data_id,
            'data_time': a.data_time, 'attempted_at': a.attempted_at, 'http_status': a.http_status,
            'category': _category(a), 'retention_policy': 'unknown'} for i, a in enumerate(entry.attempts)]
        return {'event_id': entry.event_id, 'data_id': entry.data_id, 'units': entry.units,
            'crs': entry.crs, 'cadence_minutes': entry.cadence_minutes, 'metadata_state': metadata,
            'counts': _counts(slots), 'slots': slots, 'missing_intervals': _intervals(slots),
            'days': [{'day': day, 'counts': _counts(items)} for day, items in days.items()],
            'extra_records': [{'data_time': time, 'record_count': len(refs)} for time, refs in sorted(by_time.items())],
            'source_attempts': attempts, 'baseline_grid': baseline}


def build_coverage(*, root: Path, catalog_path: Path, max_checks: int = 250,
                   max_entries: int = 10, timezone: str = 'Asia/Taipei') -> dict[str, Any]:
    if not 0 <= max_checks <= 10000 or not 1 <= max_entries <= 100:
        raise ValueError('coverage limits outside supported ranges')
    zone = ZoneInfo(timezone)
    layout = DataLayout(root)
    require_external_data_root(layout, repository_root=Path(__file__).resolve().parents[3])
    inventory = load_inventory(layout, catalog_path, max_entries)
    reader = CoverageReader(layout, max_checks)
    entries = [reader.entry(entry, metadata, zone) for entry, metadata in inventory.entries]
    totals = {key: sum(e['counts'][key] for e in entries) for key in COUNT_KEYS}
    return {'schema_version': '1.0', 'scope': 'archive_structural_coverage',
            'input_sha256': inventory.input_sha256, 'input_kind': inventory.kind,
            'reporting_timezone': timezone, 'checks_performed': reader.checked,
            'verification_budget': max_checks, 'omitted_entries': inventory.omitted_entries,
            'totals': totals, 'entries': entries, 'network_requests_performed': 0,
            'forecast_publication_ready': False, 'retention_policy': 'unknown'}
