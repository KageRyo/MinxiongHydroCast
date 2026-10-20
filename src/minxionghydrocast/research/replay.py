"""Build a bounded, read-only display snapshot from verified backtest artifacts."""

import hashlib
import re
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from minxionghydrocast.ingestion.cwa_grid import extract_cwa_grid_values
from minxionghydrocast.io.data_store import DataLayout, require_external_data_root
from minxionghydrocast.models.radar_tensor import valid_value_mask
from minxionghydrocast.models.rolling_backtest import BacktestConfig, BacktestManifest, RadarFrame, aware_time
from minxionghydrocast.pipelines.backtest_store import digest, load_record
from minxionghydrocast.pipelines.rolling_backtest import _read_forecast
from minxionghydrocast.research.replay_context import read_context
from minxionghydrocast.research.replay_io import (
    FAILURES, contained, grid_metadata, preview, verified_file,
)


def _timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('timestamp must be a timezone-aware string')
    return aware_time(value).isoformat()


def _report(layout: DataLayout, requested: Path):
    try:
        report = load_record(contained(layout, requested))
        if report['schema_version'] != '1.0' or report['scope'] != 'label_free_research_backtest':
            raise ValueError('unsupported report')
        identity = report['identity']
        config = BacktestConfig.model_validate(identity['config'])
        if digest(identity) != report['configuration_id']:
            raise ValueError('configuration identity mismatch')
        checksum = report['manifest_sha256']
        if not re.fullmatch('[0-9a-f]{64}', checksum):
            raise ValueError('invalid snapshot checksum')
        raw = layout.resolve_relative(f'backtests/manifests/{checksum}.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError('snapshot integrity failure')
        manifest = BacktestManifest.model_validate_json(raw)
        report['as_of'] = _timestamp(report['as_of'])
        report['generated_at'] = _timestamp(report['generated_at'])
        if not isinstance(report['windows'], list):
            raise ValueError('invalid windows')
        return report, config, manifest
    except FAILURES:
        raise ValueError('replay report unavailable or invalid') from None


class Replay:
    def __init__(self, layout: DataLayout, report: dict[str, Any], config: BacktestConfig,
                 manifest: BacktestManifest, size: int, allowed: set[tuple[str, str]]):
        self.layout, self.report, self.config, self.size = layout, report, config, size
        self.frames = {event.event_id: {f.data_time: f for f in event.frames} for event in manifest.events}
        self.allowed = allowed
        self.observation = lru_cache(maxsize=16)(self._observation)
        self.windows = {}
        for window in report['windows']:
            key = (window['event_id'], _timestamp(window['issue_time']))
            if key in self.windows or key[0] not in self.frames or key[1] not in self.frames[key[0]]:
                raise ValueError('replay report unavailable or invalid')
            self.windows[key] = window

    def _observation(self, event: str, time: str) -> tuple[dict, np.ndarray | None]:
        ref = self.frames[event].get(time)
        base: dict[str, Any] = {'status': 'missing', 'data_time': time, 'source': 'O-A0059-001',
                                'units': 'dBZ', 'fetched_at': None}
        array = None
        if ref is not None and (event, time) not in self.allowed:
            base['status'] = 'omitted'
        elif ref is not None and aware_time(time) <= aware_time(self.report['as_of']):
            base['sha256'] = ref.sha256
            try:
                inspection, values = extract_cwa_grid_values(verified_file(self.layout, ref))
                grid = grid_metadata(inspection)
                if (grid['data_id'] != 'O-A0059-001' or grid['units'] != 'dBZ'
                        or aware_time(inspection.data_time) != aware_time(time)):
                    raise ValueError('incompatible observation')
                array = np.asarray(values, dtype=np.float32).reshape(
                    inspection.grid_dimension_y, inspection.grid_dimension_x, 1)
                base.update(status='available', grid=grid,
                            preview=preview(array, tuple(grid['nodata_values']), self.size))
            except FileNotFoundError:
                pass
            except FAILURES:
                base['status'] = 'invalid'
        return base, array

    def _forecast(self, event: str, time: str, window: dict):
        origin = aware_time(time)
        config_id = self.report['configuration_id']
        directory = f'backtests/{config_id}/{event}/{origin:%Y%m%dT%H%M%S%fZ}'
        path = self.layout.resolve_relative(f'{directory}/forecast.npz')
        self.layout.resolve_relative(f'{directory}/forecast.json')
        if self.layout.relative(path) != window['forecast_path']:
            raise ValueError('forecast path mismatch')
        step = timedelta(minutes=self.config.cadence_minutes)
        refs = [self.frames[event][(origin - step * i).isoformat()]
                for i in range(self.config.input_length - 1, -1, -1)]
        context = {'event_id': event, 'issue_time': time, 'configuration_id': config_id,
                   'config': self.config.model_dump(mode='json'),
                   'inputs': [ref.model_dump(mode='json') for ref in refs]}
        forecast = _read_forecast(path, context)
        if forecast.record['identity'] != self.report['identity']:
            raise ValueError('code identity mismatch')
        for ref in refs:
            observation, _ = self.observation(event, ref.data_time)
            if observation.get('grid') != forecast.record['grid'] or observation['status'] != 'available':
                raise ValueError('forecast input unavailable or incompatible')
        return forecast

    def _score(self, forecast, lead: dict, target_ref: RadarFrame | None, index: int) -> dict:
        if lead['status'] not in ('scored', 'pending', 'excluded'):
            raise ValueError('unknown lead status')
        if lead['status'] == 'pending' or lead.get('reason') == 'target_file_missing':
            return {}
        if target_ref is None:
            raise ValueError('score has no target reference')
        relative = forecast.path.parent.relative_to(self.layout.root).as_posix()
        saved = load_record(self.layout.resolve_relative(f'{relative}/scores/{index:03d}.json'))
        expected = {'forecast_sha256': forecast.record['array_sha256'],
                    'target': target_ref.model_dump(mode='json'), 'lead': index}
        if saved['context'] != expected or saved['result'] != lead:
            raise ValueError('score identity mismatch')
        return saved['result'].get('metrics', {})

    def lead(self, event: str, forecast, lead: dict, index: int, time: str) -> dict:
        target_time = (aware_time(time) + timedelta(minutes=self.config.cadence_minutes * index)).isoformat()
        target, array = self.observation(event, target_time)
        result = {'lead_time_minutes': self.config.cadence_minutes * index,
                  'target_time': target_time, 'status': 'invalid', 'target': target,
                  'metrics': {}, 'models': {}}
        try:
            if lead['target_time'] != target_time or lead['lead_time_minutes'] != result['lead_time_minutes']:
                raise ValueError('lead time mismatch')
            metrics = self._score(forecast, lead, self.frames[event].get(target_time), index)
            result['status'] = target['status'] if lead['status'] == 'scored' else lead['status']
            result['reason'] = lead['reason'] if lead['reason'] in (
                '', 'target_after_as_of', 'target_not_captured', 'target_file_missing', 'no_common_valid_pixels') else 'invalid'
            nodata = tuple(forecast.record['grid']['nodata_values'])
            common = None
            if array is not None and target.get('grid') != forecast.record['grid']:
                result['status'] = 'invalid'
                result['target'] = {key: value for key, value in target.items() if key != 'preview'}
                result['target']['status'] = 'invalid'
            elif array is not None:
                common = forecast.latest_mask & valid_value_mask(array, nodata)
                common &= np.all(valid_value_mask(forecast.predictions[:, index - 1], nodata), axis=0)
                result['metrics'] = metrics
                result['status'] = lead['status']
            for i, model in enumerate(self.config.models):
                prediction = forecast.predictions[i, index - 1]
                model_data = {'preview': preview(prediction, nodata, self.size)}
                if common is not None:
                    model_data['error'] = preview(prediction - array, (), self.size, common)
                result['models'][model] = model_data
        except FAILURES:
            result['status'] = 'invalid'
        return result

    def forecast(self, event: str, time: str) -> dict:
        window = self.windows.get((event, time))
        if window is None:
            return {'status': 'missing'}
        try:
            forecast = self._forecast(event, time, window)
            if len(window['leads']) != self.config.horizon:
                raise ValueError('incomplete lead metadata')
            return {'status': 'available', 'created_at': _timestamp(forecast.record['created_at']),
                    'mode': 'retrospective_replay', 'sha256': forecast.record['array_sha256'],
                    'grid': forecast.record['grid'], 'leads': [
                        self.lead(event, forecast, lead, i, time)
                        for i, lead in enumerate(window['leads'], 1)]}
        except FAILURES:
            return {'status': 'invalid'}


    def event(self, event_id: str, context: list[dict], budget: int) -> tuple[dict, int]:
        frames = []
        used = 0
        for time in self.frames[event_id]:
            if (event_id, time) not in self.allowed:
                continue
            forecast = {'status': 'missing'}
            if (event_id, time) in self.windows:
                forecast = {'status': 'omitted'}
                if used < budget:
                    forecast = self.forecast(event_id, time)
                    used += 1
            observation, _ = self.observation(event_id, time)
            frames.append({'data_time': time, 'fetched_at': None,
                           'observation': observation, 'forecast': forecast})
        return {'event_id': event_id, 'frames': frames, 'context': context}, used


def build_replay(*, root: Path, report_path: Path = Path('backtests/latest.json'),
                 context_path: Path | None = None, preview_size: int = 160,
                 max_frames: int = 120, max_windows: int = 24) -> dict[str, Any]:
    if not 1 <= preview_size <= 320 or not 1 <= max_frames <= 500 or not 1 <= max_windows <= 100:
        raise ValueError('replay limits outside supported ranges')
    layout = DataLayout(root)
    require_external_data_root(layout, repository_root=Path(__file__).resolve().parents[3])
    report, config, manifest = _report(layout, report_path)
    cells = preview_size ** 2 * (max_frames + max_windows * config.horizon * (2 * len(config.models) + 1))
    if cells > 24_000_000:
        raise ValueError('combined replay preview budget exceeded; reduce export limits')
    eligible = [(e.event_id, f.data_time) for e in manifest.events for f in e.frames
                if aware_time(f.data_time) <= aware_time(report['as_of'])]
    allowed = set(eligible[:max_frames])
    try:
        reader = Replay(layout, report, config, manifest, preview_size, allowed)
    except FAILURES:
        raise ValueError('replay report unavailable or invalid') from None
    contexts, omitted_context = read_context(layout, context_path, preview_size, set(reader.frames))
    events = []
    windows_used = 0
    for event in manifest.events:
        display, used = reader.event(event.event_id, contexts.get(event.event_id, []), max_windows - windows_used)
        events.append(display)
        windows_used += used
    return {'schema_version': '1.0', 'scope': 'offline_research_replay', 'events': events,
            'models': config.models, 'cadence_minutes': config.cadence_minutes,
            'horizon': config.horizon, 'configuration_id': report['configuration_id'],
            'report_sha256': digest(report), 'manifest_sha256': report['manifest_sha256'],
            'as_of': report['as_of'], 'report_generated_at': report['generated_at'],
            'preview_size': preview_size, 'omitted_frames': sum(len(e.frames) for e in manifest.events) - len(allowed),
            'omitted_windows': len(reader.windows) - windows_used,
            'omitted_context_artifacts': omitted_context, 'forecast_publication_ready': False}
