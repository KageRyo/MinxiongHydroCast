"""Optional checksum-pinned hourly QPE and gauge context, always segregated."""

import re
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field, field_validator, model_validator

from minxionghydrocast.ingestion.cwa_grid import extract_cwa_grid_values
from minxionghydrocast.io.data_store import DataLayout
from minxionghydrocast.models.rolling_backtest import Contract, RadarFrame, aware_time
from minxionghydrocast.pipelines.qpe_gauge_validation import load_gauge_observations
from minxionghydrocast.research.replay_io import (
    FAILURES, contained, grid_metadata, preview, verified_file,
)


class ContextArtifact(RadarFrame):
    event_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
    kind: Literal['qpe', 'gauges']
    interval_minutes: Literal[60]
    fetched_at: str | None = None

    @field_validator('fetched_at')
    @classmethod
    def fetched_time(cls, value: str | None) -> str | None:
        return aware_time(value).isoformat() if value is not None else None


class ContextManifest(Contract):
    schema_version: Literal['1.0']
    artifacts: list[ContextArtifact] = Field(max_length=1000)

    @model_validator(mode='after')
    def unique(self):
        keys = [(a.event_id, a.kind, a.data_time) for a in self.artifacts]
        if len(set(keys)) != len(keys):
            raise ValueError('duplicate context identity')
        return self


def _qpe(layout: DataLayout, ref: ContextArtifact, size: int) -> dict[str, Any]:
    inspection, values = extract_cwa_grid_values(verified_file(layout, ref))
    grid = grid_metadata(inspection)
    if (inspection.data_id != 'O-B0045-001' or inspection.units != 'mm'
            or aware_time(inspection.data_time) != aware_time(ref.data_time)):
        raise ValueError('QPE time or product mismatch')
    array = np.asarray(values).reshape(inspection.grid_dimension_y, inspection.grid_dimension_x)
    return {'grid': grid, 'preview': preview(array, inspection.nodata_values, size)}


def _gauges(layout: DataLayout, ref: ContextArtifact) -> dict[str, Any]:
    gauges = load_gauge_observations(verified_file(layout, ref), rainfall_keys=(
        'Past1hr', 'Past1Hr', 'Past1Hour', 'past1hr', 'past1Hour', 'hourlyRainfall'))
    if not gauges:
        raise ValueError('no declared hourly gauge readings')
    stations = []
    for gauge in gauges:
        if (aware_time(gauge.data_time) != aware_time(ref.data_time)
                or gauge.crs not in ('WGS84', 'TWD67', 'EPSG:4326', 'EPSG:3821')
                or not np.isfinite([gauge.latitude, gauge.longitude, gauge.rainfall_mm]).all()
                or not -90 <= gauge.latitude <= 90 or not -180 <= gauge.longitude <= 180
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', gauge.station_id)):
            raise ValueError('incompatible gauge metadata')
        stations.append({'station_id': gauge.station_id, 'latitude': gauge.latitude,
                         'longitude': gauge.longitude, 'crs': gauge.crs, 'mm': gauge.rainfall_mm})
    return {'stations': stations[:200], 'omitted_stations': max(0, len(stations) - 200)}


def read_context(layout: DataLayout, path: Path | None, size: int,
                 event_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    if path is None:
        return {}
    try:
        manifest = ContextManifest.model_validate_json(contained(layout, path).read_bytes())
    except FAILURES:
        raise ValueError('replay context unavailable or invalid') from None
    result: dict[str, list[dict[str, Any]]] = {}
    for ref in manifest.artifacts:
        if ref.event_id not in event_ids:
            continue
        item = {'kind': ref.kind, 'data_time': ref.data_time, 'fetched_at': ref.fetched_at,
                'interval_minutes': ref.interval_minutes, 'units': 'mm', 'overlay': False,
                'source': 'O-B0045-001' if ref.kind == 'qpe' else 'O-A0002-001',
                'sha256': ref.sha256, 'status': 'available'}
        try:
            item.update(_qpe(layout, ref, size) if ref.kind == 'qpe' else _gauges(layout, ref))
        except FileNotFoundError:
            item['status'] = 'missing'
        except FAILURES:
            item['status'] = 'invalid'
        result.setdefault(ref.event_id, []).append(item)
    return result
