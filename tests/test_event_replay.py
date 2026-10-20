import hashlib
import json
from pathlib import Path

import pytest

from minxionghydrocast.pipelines.backtest_store import load_record, save_record
from test_rolling_backtest import frame, manifest, run


def prepared(tmp_path):
    root = tmp_path / 'external'
    refs = [frame(root, i) for i in range(4)]
    report = run(manifest(root, refs), root, max_new_windows=1)
    return root, report


def replay(root, **kwargs):
    from minxionghydrocast.research.replay import build_replay
    return build_replay(root=root, **kwargs)


def test_replay_uses_verified_saved_forecasts_metrics_and_native_errors(tmp_path):
    root, report = prepared(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = replay(root)
    event = result['events'][0]
    assert event['event_id'] == 'event_one'
    assert len(event['frames']) == 4
    origin = event['frames'][1]
    assert origin['observation']['preview']['values'] == [10, 10, 10, 10]
    forecast = origin['forecast']
    assert forecast['status'] == 'available'
    lead = forecast['leads'][0]
    assert lead['target']['preview']['values'] == [20, 20, 20, 20]
    assert lead['models']['persistence']['preview']['values'] == [10, 10, 10, 10]
    assert lead['models']['persistence']['error']['values'] == [-10, -10, -10, -10]
    assert lead['metrics'] == report['windows'][0]['leads'][0]['metrics']
    assert origin['fetched_at'] is None
    assert forecast['created_at'] != origin['data_time']
    assert event['frames'][0]['forecast']['status'] == 'missing'
    assert 'O-A0059-001' in json.dumps(result)
    assert str(root) not in json.dumps(result)
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('kind', ['source_missing', 'source_corrupt', 'array_corrupt', 'score_corrupt'])
def test_corrupt_or_missing_artifacts_are_explicit_without_private_paths(tmp_path, kind):
    root, report = prepared(tmp_path)
    forecast = root / report['windows'][0]['forecast_path']
    paths = {'source_missing': root / 'frames/2.json', 'source_corrupt': root / 'frames/2.json',
             'array_corrupt': forecast, 'score_corrupt': forecast.parent / 'scores/001.json'}
    if kind == 'source_missing':
        paths[kind].unlink()
    else:
        paths[kind].write_bytes(b'corrupted /private/host?api_key=secret')
    result = replay(root)
    lead = result['events'][0]['frames'][1]['forecast']
    if kind == 'array_corrupt':
        assert lead['status'] == 'invalid'
    elif kind == 'score_corrupt':
        assert lead['leads'][0]['status'] == 'invalid'
        assert lead['leads'][0]['metrics'] == {}
    else:
        expected = 'missing' if kind == 'source_missing' else 'invalid'
        assert lead['leads'][0]['target']['status'] == expected
        assert lead['leads'][0]['metrics'] == {}
    exported = json.dumps(result)
    assert str(root) not in exported
    assert 'api_key' not in exported


@pytest.mark.parametrize('kind', ['report', 'snapshot', 'escape'])
def test_invalid_top_level_contract_fails_with_safe_diagnostic(tmp_path, kind):
    root, _ = prepared(tmp_path)
    report = root / 'backtests/latest.json'
    if kind == 'report':
        report.write_text('secret invalid JSON')
    elif kind == 'snapshot':
        record = load_record(report)
        (root / 'backtests/manifests' / (record['manifest_sha256'] + '.json')).write_text('bad')
    else:
        outside = tmp_path / 'private.json'
        outside.write_bytes(report.read_bytes())
        report.unlink()
        report.symlink_to(outside)
    with pytest.raises(ValueError, match='replay report unavailable or invalid') as error:
        replay(root)
    assert str(root) not in str(error.value)


def test_export_limits_disclose_omitted_data_before_loading(tmp_path):
    root, _ = prepared(tmp_path)
    result = replay(root, max_frames=2, max_windows=1, preview_size=1)
    assert result['omitted_frames'] == 2
    assert result['events'][0]['frames'][1]['observation']['preview']['width'] == 1
    assert result['events'][0]['frames'][1]['observation']['grid']['grid_dimension_x'] == 2


def test_forecast_path_or_saved_metric_drift_cannot_be_presented_as_verified(tmp_path):
    root, _ = prepared(tmp_path)
    path = root / 'backtests/latest.json'
    record = load_record(path)
    record['windows'][0]['leads'][0]['metrics']['persistence']['rmse'] = 999
    save_record(path, record)
    result = replay(root)
    lead = result['events'][0]['frames'][1]['forecast']['leads'][0]
    assert lead['status'] == 'invalid'
    assert lead['metrics'] == {}


def test_context_is_separate_hourly_mm_and_preserves_known_datum(tmp_path):
    from test_qpe_gauge_validation import write_qpe_grid, write_gauges
    root, _ = prepared(tmp_path)
    artifacts = []
    for kind, writer in [('qpe', write_qpe_grid), ('gauges', write_gauges)]:
        path = root / f'{kind}.json'
        writer(path)
        artifacts.append({'kind': kind, 'event_id': 'event_one', 'path': path.name,
                          'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'data_time': '2026-07-02T15:00:00+08:00', 'interval_minutes': 60})
    context = root / 'context.json'
    context.write_text(json.dumps({'schema_version': '1.0', 'artifacts': artifacts}))
    result = replay(root, context_path=Path('context.json'))
    contexts = result['events'][0]['context']
    assert contexts[0]['kind'] == 'qpe'
    assert contexts[0]['status'] == 'available'
    assert contexts[0]['units'] == 'mm'
    assert contexts[0]['interval_minutes'] == 60
    assert contexts[0]['grid']['crs'] == 'TWD67經緯網格'
    assert contexts[1]['kind'] == 'gauges'
    assert 'preview' not in contexts[1]
    assert contexts[1]['overlay'] is False


def test_context_rejects_ambiguous_accumulation_and_path_escapes(tmp_path):
    root, _ = prepared(tmp_path)
    context = root / 'context.json'
    artifact = {'kind': 'qpe', 'event_id': 'event_one', 'path': '../private.json',
                'bytes': 1, 'sha256': '0' * 64, 'data_time': '2026-07-01T00:00:00Z',
                'interval_minutes': 10}
    context.write_text(json.dumps({'schema_version': '1.0', 'artifacts': [artifact]}))
    with pytest.raises(ValueError, match='replay context unavailable or invalid'):
        replay(root, context_path=Path('context.json'))
