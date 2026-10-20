"""Root-contained artifact reads and bounded native-grid display previews."""

from pathlib import Path
from typing import Any

import numpy as np

from minxionghydrocast.ingestion.cwa_grid import CwaGridInspection
from minxionghydrocast.io.data_store import DataLayout, sha256_file
from minxionghydrocast.models.radar_tensor import valid_value_mask
from minxionghydrocast.models.rolling_backtest import RadarFrame

FAILURES = (OSError, ValueError, KeyError, TypeError, IndexError)


def contained(layout: DataLayout, requested: Path) -> Path:
    requested = requested.expanduser()
    if requested.is_absolute():
        requested = requested.resolve().relative_to(layout.root)
    return layout.resolve_relative(requested.as_posix())


def verified_file(layout: DataLayout, ref: RadarFrame) -> Path:
    path = layout.resolve_relative(ref.path)
    if not path.is_file():
        raise FileNotFoundError
    if path.stat().st_size != ref.bytes or sha256_file(path) != ref.sha256:
        raise ValueError('source integrity failure')
    return path


def grid_metadata(inspection: CwaGridInspection) -> dict[str, Any]:
    if (not inspection.valid or inspection.grid_dimension_x < 1 or inspection.grid_dimension_y < 1
            or inspection.crs not in ('TWD67', 'TWD67經緯網格', 'WGS84', 'EPSG:4326', 'EPSG:3821')
            or not np.isfinite([inspection.grid_resolution, inspection.start_latitude,
                                inspection.start_longitude]).all()
            or inspection.grid_resolution <= 0):
        raise ValueError('invalid native grid')
    grid = {key: getattr(inspection, key) for key in (
        'data_id', 'units', 'crs', 'start_longitude', 'start_latitude', 'grid_resolution',
        'grid_dimension_x', 'grid_dimension_y', 'nodata_values')}
    grid['nodata_values'] = list(grid['nodata_values'])
    return grid


def preview(values: np.ndarray, nodata: tuple[float, ...], size: int,
            mask: np.ndarray | None = None) -> dict[str, Any]:
    values = np.asarray(values).squeeze(axis=-1) if values.ndim == 3 else np.asarray(values)
    valid = valid_value_mask(values, nodata)
    if mask is not None:
        valid &= mask.reshape(values.shape)
    stride = max(1, int(np.ceil(max(values.shape) / size)))
    sampled, sampled_mask = values[::stride, ::stride], valid[::stride, ::stride]
    data = [float(value) if ok else None for value, ok in zip(sampled.flat, sampled_mask.flat)]
    return {'width': sampled.shape[1], 'height': sampled.shape[0], 'stride': stride,
            'sampling': 'nearest_native_rows_columns', 'values': data}
