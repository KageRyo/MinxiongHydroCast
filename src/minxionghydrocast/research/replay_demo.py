"""Credential-free synthetic fixtures processed by the real backtest and replay readers."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from minxionghydrocast.models.rolling_backtest import BacktestConfig
from minxionghydrocast.pipelines.rolling_backtest import run_backtest
from minxionghydrocast.research.replay import build_replay

START = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _grid(time: str, values: list[float], product='O-A0059-001') -> dict:
    return {'cwaopendata': {'dataid': product, 'sent': time, 'dataset': {
        'datasetInfo': {'datasetDescription': 'synthetic demonstration', 'parameterSet': {
            'DateTime': time, 'GridDimensionX': 24, 'GridDimensionY': 24,
            'StartPointLongitude': 120.0, 'StartPointLatitude': 23.0, 'GridResolution': 0.01,
            ('Reflectivity' if product == 'O-A0059-001' else 'Precipitation'):
                'dBZ' if product == 'O-A0059-001' else 'mm'}},
        'contents': {'contentDescription': '資料無效值為-999。使用之座標系統為TWD67。',
                     'content': ','.join(map(str, values))}}}}


def _write(root: Path, name: str, payload: dict, time: str) -> dict:
    raw = json.dumps(payload).encode()
    (root / name).write_bytes(raw)
    return {'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'data_time': time}


def build_demo(**limits) -> dict:
    with TemporaryDirectory(prefix='mhc-replay-demo-') as temporary:
        root = Path(temporary)
        events = []
        yy, xx = np.mgrid[:24, :24]
        for day, event_id, indices in [(0, 'synthetic_moving_cell', [0, 1, 2, 4]),
                                       (1, 'synthetic_no_forecasts', [0, 1])]:
            frames = []
            for i in indices:
                time = (START + timedelta(days=day, minutes=i * 10)).isoformat()
                values = 55 * np.exp(-((xx - 7 - i) ** 2 + (yy - 12) ** 2) / 18)
                values[:2, :2] = -999
                frames.append(_write(root, f'{event_id}_{i}.json',
                                     _grid(time, values.ravel().tolist()), time))
            events.append({'event_id': event_id, 'frames': frames})
        manifest = root / 'manifest.json'
        manifest.write_text(json.dumps({'schema_version': '1.0', 'events': events}))
        run_backtest(root=root, manifest_path=manifest, max_new_windows=2,
                     config=BacktestConfig(input_length=2, horizon=3, min_valid_pixels=4))
        time = (START + timedelta(minutes=20)).isoformat()
        qpe = _write(root, 'qpe.json', _grid(time, (np.maximum(values, 0) / 5).ravel().tolist(),
                                           product='O-B0045-001'), time)
        gauges = _write(root, 'gauges.json', {'records': {'Station': [
            {'StationId': 'DEMO01', 'ObsTime': {'DateTime': time},
             'GeoInfo': {'Coordinates': [{'CoordinateName': 'WGS84', 'StationLatitude': 23.1,
                                          'StationLongitude': 120.1}]}, 'RainfallElement': {'Past1hr': 6.5}}
        ]}}, time)
        context = []
        for kind, ref in [('qpe', qpe), ('gauges', gauges)]:
            context.append({**ref, 'kind': kind, 'event_id': events[0]['event_id'],
                            'interval_minutes': 60, 'fetched_at': (START + timedelta(minutes=22)).isoformat()})
        (root / 'context.json').write_text(json.dumps({'schema_version': '1.0', 'artifacts': context}))
        result = build_replay(root=root, context_path=Path('context.json'), **limits)
        result['demo'] = True
        return result
