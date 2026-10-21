"""Synthetic archive health example using the native official radar schema."""

import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from minxionghydrocast.research.archive_coverage import build_coverage
from minxionghydrocast.research.replay_demo import START, _grid, _write


def build_coverage_demo(**options) -> dict:
    with TemporaryDirectory(prefix='mhc-coverage-demo-') as temporary:
        root = Path(temporary)
        refs = []
        for index in [0, 2, 3, 4, 5]:
            time = (START + timedelta(minutes=10 * index)).isoformat()
            values = [float(index)] * 576 if index != 5 else [-999.0] * 576
            payload = _grid(time, values)
            if index == 4:
                payload['cwaopendata']['dataset']['datasetInfo']['parameterSet']['StartPointLongitude'] = 121.0
            ref = _write(root, f'{index}.json', payload, time)
            refs.append(ref)
        (root / refs[1]['path']).write_bytes(b'corrupt')
        duplicate = {**refs[2], 'path': 'duplicate.json'}
        (root / duplicate['path']).write_bytes((root / refs[2]['path']).read_bytes())
        refs.append(duplicate)
        attempts = [{'data_time': START.isoformat(), 'attempted_at': START.isoformat(),
                     'http_status': status, 'failure_kind': kind} for status, kind in [
                         (404, 'http'), (403, 'http'), (429, 'http'), (None, 'transport')]]
        entry = {'event_id': 'synthetic_archive', 'data_id': 'O-A0059-001',
                 'start_time': START.isoformat(), 'end_time': (START + timedelta(minutes=50)).isoformat(),
                 'cadence_minutes': 10, 'units': 'dBZ', 'crs': 'TWD67', 'frames': refs, 'attempts': attempts}
        (root / 'inventory.json').write_text(json.dumps({'schema_version': '1.0', 'kind': 'archive_inventory', 'entries': [entry]}))
        report = build_coverage(root=root, catalog_path=Path('inventory.json'), **options)
        report['demo'] = True
        return report
