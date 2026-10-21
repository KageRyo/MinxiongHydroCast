import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from test_rolling_backtest import START, frame


def native(root, index, *, values=None, **params):
    ref = frame(root, index, values, **params)
    return {**ref}


def inventory(root, refs, *, end=4, attempts=None):
    path = root / 'inventory.json'
    entry = {'event_id': 'event_one', 'data_id': 'O-A0059-001',
             'start_time': START.isoformat(), 'end_time': (START + timedelta(minutes=end * 10)).isoformat(),
             'cadence_minutes': 10, 'units': 'dBZ', 'crs': 'TWD67', 'frames': refs,
             'attempts': attempts or []}
    path.write_text(json.dumps({'schema_version': '1.0', 'kind': 'archive_inventory', 'entries': [entry]}))
    return path


def report(root, **kwargs):
    from minxionghydrocast.research.archive_coverage import build_coverage
    return build_coverage(root=root, catalog_path=Path('inventory.json'), **kwargs)


def test_counts_distinguish_presence_integrity_and_scientific_structure(tmp_path):
    root = tmp_path / 'external'
    refs = [native(root, 0), native(root, 2), native(root, 3, values=[-999] * 4), native(root, 4)]
    corrupted = root / refs[1]['path']
    raw = corrupted.read_bytes()
    corrupted.write_bytes(raw[:-1] + b'!')
    duplicate = {**refs[-1], 'path': 'frames/duplicate.json'}
    (root / duplicate['path']).write_bytes((root / refs[-1]['path']).read_bytes())
    refs.append(duplicate)
    inventory(root, refs)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = report(root)
    entry = result['entries'][0]
    assert entry['counts'] == {'expected': 5, 'present': 4, 'size_verified': 4,
        'checksum_verified': 3, 'usable': 1, 'missing': 1, 'duplicates': 1, 'unchecked': 0}
    assert [slot['state'] for slot in entry['slots']] == [
        'usable', 'uncaptured', 'checksum_mismatch', 'all_nodata', 'duplicate_timestamp']
    assert entry['missing_intervals'] == [{'start_time': '2026-07-01T00:10:00+00:00',
                                         'end_time': '2026-07-01T00:10:00+00:00', 'count': 1}]
    assert entry['days'][0]['day'] == '2026-07-01'
    assert result['network_requests_performed'] == 0
    assert result['forecast_publication_ready'] is False
    assert str(root) not in json.dumps(result)
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert report(root) == result


@pytest.mark.parametrize(('changes', 'state'), [
    ({'Reflectivity': 'mm'}, 'units_changed'),
    ({'StartPointLongitude': 121.0}, 'grid_changed'),
    ({'DateTime': '2026-07-01T01:00:00Z'}, 'time_mismatch')])
def test_checksum_valid_header_drift_is_unusable(tmp_path, changes, state):
    root = tmp_path / 'external'
    refs = [native(root, 0), native(root, 1, **changes)]
    inventory(root, refs, end=1)
    result = report(root)['entries'][0]
    assert result['counts']['checksum_verified'] == 2
    assert result['counts']['usable'] == 1
    assert result['slots'][1]['state'] == state


def test_budget_marks_unchecked_and_never_calls_it_verified(tmp_path):
    root = tmp_path / 'external'
    inventory(root, [native(root, i) for i in range(4)], end=3)
    result = report(root, max_checks=1)
    assert result['checks_performed'] == 1
    counts = result['entries'][0]['counts']
    assert counts['present'] == 4
    assert counts['checksum_verified'] == counts['usable'] == 1
    assert counts['unchecked'] == 3
    assert counts['missing'] == 0


def test_duplicate_outside_window_and_off_cadence_do_not_inflate_counts(tmp_path):
    root = tmp_path / 'external'
    refs = [native(root, 0), native(root, 1), native(root, 5)]
    ref = native(root, 2)
    ref['data_time'] = '2026-07-01T00:15:00Z'
    refs.append(ref)
    inventory(root, refs, end=1)
    entry = report(root)['entries'][0]
    assert entry['counts']['expected'] == entry['counts']['usable'] == 2
    assert len(entry['extra_records']) == 2


def test_missing_and_escaped_files_have_safe_states(tmp_path):
    root = tmp_path / 'external'
    refs = [native(root, 0), native(root, 1)]
    outside = tmp_path / 'secret.json'
    source = root / refs[0]['path']
    outside.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(outside)
    (root / refs[1]['path']).unlink()
    inventory(root, refs, end=1)
    entry = report(root)['entries'][0]
    assert [s['state'] for s in entry['slots']] == ['path_escape', 'file_missing']
    assert 'secret' not in json.dumps(entry)


def test_source_attempt_categories_do_not_export_urls_or_error_text(tmp_path):
    root = tmp_path / 'external'
    ref = native(root, 0)
    attempts = [{'data_time': ref['data_time'], 'attempted_at': ref['data_time'],
                 'http_status': status, 'failure_kind': kind}
                for status, kind in [(404, 'http'), (401, 'http'), (429, 'http'), (None, 'timeout')]]
    inventory(root, [ref], end=0, attempts=attempts)
    source = report(root)['entries'][0]['source_attempts']
    assert [s['category'] for s in source] == ['http_not_found', 'authentication', 'rate_limit', 'transport']
    assert all(s['retention_policy'] == 'unknown' for s in source)
    assert [s['record_index'] for s in source] == [0, 1, 2, 3]


def test_day_grouping_uses_declared_reporting_timezone(tmp_path):
    root = tmp_path / 'external'
    refs = [native(root, 0), native(root, 1)]
    path = inventory(root, refs, end=1)
    payload = json.loads(path.read_text())
    payload['entries'][0]['start_time'] = '2026-07-01T23:50:00+00:00'
    payload['entries'][0]['end_time'] = '2026-07-02T00:00:00+00:00'
    payload['entries'][0]['frames'] = []
    path.write_text(json.dumps(payload))
    assert [d['day'] for d in report(root, timezone='UTC')['entries'][0]['days']] == ['2026-07-01', '2026-07-02']
    assert [d['day'] for d in report(root)['entries'][0]['days']] == ['2026-07-02']


def test_malformed_inventory_and_outside_catalog_have_fixed_diagnostic(tmp_path):
    from minxionghydrocast.research.archive_coverage import build_coverage
    root = tmp_path / 'external'
    root.mkdir()
    path = root / 'inventory.json'
    path.write_text('{secret')
    with pytest.raises(ValueError, match='archive inventory unavailable or invalid'):
        report(root)
    with pytest.raises(ValueError, match='archive inventory unavailable or invalid'):
        build_coverage(root=root, catalog_path=tmp_path / 'private.json')


def catalog_fixture(root, kind):
    from test_dataset_build import manifest_payload
    from test_event_discovery import trigger_metric
    refs = [native(root, i) for i in range(3)]
    event_id = 'event_one' if kind == 'discovery' else 'train_one'
    collection = {'event_id': event_id, 'data_id': 'O-A0059-001', 'frame_count': 3,
                  'bytes_written': sum(r['bytes'] for r in refs), 'frames': [
        {'data_time': r['data_time'], 'source_url': 'https://private.test/?Authorization=secret',
         'output_path': str(root / r['path']), 'bytes_written': r['bytes']} for r in refs]}
    collection_path = root / 'collection.json'
    collection_path.write_text(json.dumps(collection))
    def artifact(path, label):
        return {'kind': label, 'path': path.relative_to(root).as_posix(),
                'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    collection_ref = artifact(collection_path, 'event_collection')
    raw_refs = [artifact(root / r['path'], 'raw_radar_frame') for r in refs]
    common = {'data_root': str(root), 'schema_version': '1.0'}
    if kind == 'discovery':
        from minxionghydrocast.models.event_evidence_schemas import DiscoveryConfig
        candidate = {'candidate_id': event_id, 'operational_status': 'awaiting_review',
            'first_trigger_time': refs[1]['data_time'], 'last_trigger_time': refs[1]['data_time'],
            'window_start_time': refs[0]['data_time'], 'window_end_time': refs[2]['data_time'],
            'candidate_labels': ['minxiong_35dbz', 'taiwan_wide_35dbz'],
            'triggers': [trigger_metric(refs[1]['data_time']).model_dump(mode='json')],
            'radar_collection': {'expected_frame_count': 3, 'captured_frame_count': 3,
                'missing_data_times': [], 'frames': raw_refs, 'collection': collection_ref,
                'plan': collection_ref, 'complete': True}}
        payload = {**common, 'updated_at': refs[-1]['data_time'], 'config': DiscoveryConfig().model_dump(mode='json'),
                   'cursor': {}, 'candidates': [candidate]}
    else:
        source_manifest = manifest_payload()
        source_manifest['events'][0].update(start_time=refs[0]['data_time'], end_time=refs[-1]['data_time'])
        path = root / 'source_manifest.json'
        path.write_text(json.dumps(source_manifest))
        binary = {'hits': 0, 'misses': 0, 'false_alarms': 0, 'correct_negatives': 4,
                  'csi': 0.0, 'pod': 0.0, 'far': 0.0}
        metrics = {'rmse': 0.0, 'csi': 0.0, 'pod': 0.0, 'far': 0.0, 'lead_time_metrics': [
            {'lead_index': 0, 'lead_time_minutes': 10, 'rmse': 0.0, 'event_metrics': binary,
             'valid_pixel_count': 4, 'ignored_pixel_count': 0}]}
        payload = {**common, 'generated_at': refs[-1]['data_time'], 'dataset_id': 'synthetic_archive',
            'source_data_id': 'O-A0059-001', 'manifest': artifact(path, 'manifest'),
            'history_index': collection_ref, 'split_counts': {'train': 1, 'validation': 0, 'test': 0},
            'combined_archives': {s: collection_ref for s in ('train', 'validation', 'test')},
            'forecast_publication_blockers': ['research_only'], 'events': [
                {'event_id': event_id, 'split': 'train', 'region': 'Taiwan',
                 'source_data_id': 'O-A0059-001', 'start_time': refs[0]['data_time'],
                 'end_time': refs[-1]['data_time'], 'frame_count': 3, 'window_count': 1,
                 'artifacts': [collection_ref, *raw_refs], 'persistence': metrics}]}
    path = root / 'inventory.json'
    path.write_text(json.dumps(payload))
    return collection_path


@pytest.mark.parametrize('kind', ['discovery', 'dataset'])
def test_existing_catalogs_reuse_pinned_collections_without_exporting_secrets(tmp_path, kind):
    root = tmp_path / 'external'
    catalog_fixture(root, kind)
    result = report(root)
    assert result['totals']['usable'] == result['totals']['expected'] == 3
    assert result['entries'][0]['metadata_state'] == 'verified'
    assert 'Authorization' not in json.dumps(result)
    assert 'private.test' not in json.dumps(result)


@pytest.mark.parametrize('kind', ['discovery', 'dataset'])
def test_missing_collection_metadata_is_unknown_not_confirmed_missing(tmp_path, kind):
    root = tmp_path / 'external'
    path = catalog_fixture(root, kind)
    path.unlink()
    result = report(root)
    assert result['totals']['missing'] == 0
    assert result['totals']['unchecked'] == 3
    assert result['entries'][0]['metadata_state'] == 'invalid'


@pytest.mark.parametrize('format_name', ['json', 'table', 'html'])
def test_demo_cli_exports_inspectable_reports_without_network(tmp_path, format_name):
    from minxionghydrocast import cli
    suffix = {'json': 'json', 'table': 'txt', 'html': 'html'}[format_name]
    path = tmp_path / ('coverage.' + suffix)
    cli.main(['data', 'archive-coverage', '--demo', '--format', format_name, '--output', str(path)])
    text = path.read_text()
    if format_name == 'json':
        payload = json.loads(text)
        assert payload['totals']['expected'] == 6
        assert payload['totals']['usable'] == 1
        assert payload['network_requests_performed'] == 0
    else:
        assert 'Expected' in text
        assert 'Usable' in text
        assert 'synthetic_archive' in text
    assert str(tmp_path) not in text


def test_coverage_export_never_overwrites_and_escapes_html(tmp_path):
    from minxionghydrocast.research.coverage_view import render_html, write_coverage
    root = tmp_path / 'external'
    inventory(root, [native(root, 0)], end=0)
    result = report(root)
    path = tmp_path / 'coverage.json'
    write_coverage(result, path, root=root, format_name='json')
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_coverage(result, path, root=root, format_name='json')
    assert path.read_bytes() == original
    result['entries'][0]['event_id'] = '<script>alert(1)</script>'
    html = render_html(result)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


def test_coverage_output_outside_permitted_roots_is_rejected(tmp_path):
    from minxionghydrocast.research.coverage_view import write_coverage
    with pytest.raises(ValueError):
        write_coverage({}, Path('/etc/coverage.json'), root=tmp_path, format_name='json')


def test_duplicate_slot_retains_unchecked_budget_state(tmp_path):
    root = tmp_path / 'external'
    ref = native(root, 0)
    inventory(root, [ref, ref], end=0)
    entry = report(root, max_checks=0)['entries'][0]
    assert entry['counts']['duplicates'] == 1
    assert entry['counts']['unchecked'] == 1
    assert entry['counts']['usable'] == 0


def test_non_object_inventory_has_fixed_diagnostic(tmp_path):
    root = tmp_path / 'external'
    root.mkdir()
    (root / 'inventory.json').write_text('[]')
    with pytest.raises(ValueError, match='archive inventory unavailable or invalid'):
        report(root)


def test_impossible_native_coordinates_are_structurally_invalid(tmp_path):
    root = tmp_path / 'external'
    inventory(root, [native(root, 0, StartPointLatitude=123.0)], end=0)
    result = report(root)
    assert result['totals']['checksum_verified'] == 1
    assert result['totals']['usable'] == 0


def test_conflicting_catalog_pins_are_metadata_failure_not_usable(tmp_path):
    root = tmp_path / 'external'
    catalog_fixture(root, 'dataset')
    path = root / 'inventory.json'
    payload = json.loads(path.read_text())
    artifacts = payload['events'][0]['artifacts']
    ref = next(a for a in artifacts if a['kind'] == 'raw_radar_frame')
    artifacts.insert(0, {**ref, 'sha256': '0' * 64})
    path.write_text(json.dumps(payload))
    entry = report(root)['entries'][0]
    assert entry['metadata_state'] == 'invalid'
    assert entry['counts']['checksum_verified'] == entry['counts']['usable'] == 0


def test_in_root_symlink_preserves_original_catalog_checksum(tmp_path):
    root = tmp_path / 'external'
    catalog_fixture(root, 'dataset')
    path = root / 'frames/0.json'
    target = root / 'preserved.json'
    path.rename(target)
    path.symlink_to(target)
    result = report(root)
    assert result['totals']['checksum_verified'] == result['totals']['usable'] == 3


def test_duplicate_timestamp_can_also_be_confirmed_missing(tmp_path):
    root = tmp_path / 'external'
    ref = native(root, 0)
    inventory(root, [ref, ref], end=0)
    (root / ref['path']).unlink()
    entry = report(root)['entries'][0]
    assert entry['counts']['duplicates'] == 1
    assert entry['counts']['missing'] == 1
    assert entry['missing_intervals'][0]['count'] == 1
