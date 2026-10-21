"""Plain-text and script-free offline HTML views of the same coverage report."""

import base64
import hashlib
import json
from html import escape
from pathlib import Path

from minxionghydrocast.research.archive_coverage import COUNT_KEYS
from minxionghydrocast.research.report_export import write_new_report

LABELS = {'expected': 'Expected', 'present': 'Present', 'size_verified': 'Size verified',
          'checksum_verified': 'SHA-256 verified', 'usable': 'Usable', 'missing': 'Missing',
          'duplicates': 'Duplicate times', 'unchecked': 'Unchecked'}
STYLE = '''
:root{font:16px/1.5 system-ui,sans-serif;color:#202428;background:#f4f6f7;color-scheme:light}
*{box-sizing:border-box}body{margin:0;min-width:320px}header{background:#202428;color:white;padding:24px;border-bottom:4px solid #4a6572}h1{font-size:24px;margin:0}header p{margin:4px 0 0;color:#d4dce1}main{max-width:1440px;margin:auto;padding:24px 20px 48px}h2{font-size:19px;margin:0 0 12px}.notice{background:#fff8e8;border-left:4px solid #9b5c00;padding:12px 16px;margin-bottom:22px}.summary{display:flex;flex-wrap:wrap;background:white;border:1px solid #cbd3d8;margin:0 0 24px}.summary div{padding:14px 20px;flex:1;min-width:130px}.summary dt{color:#53616b;font-size:13px}.summary dd{margin:4px 0 0;font-weight:650;font-size:25px;font-variant-numeric:tabular-nums}section,details{background:white;border:1px solid #cbd3d8;padding:16px;margin:18px 0}summary{cursor:pointer;font-weight:600;min-height:44px;overflow-wrap:anywhere}:focus-visible{outline:3px solid #2164a5;outline-offset:3px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}caption{text-align:left;color:#53616b;margin:8px 0}td,th{text-align:left;padding:9px 12px;border-bottom:1px solid #e2e7eb;white-space:nowrap}thead{background:#edf2f5}th{font-weight:600}.meta{font-size:13px;color:#53616b;overflow-wrap:anywhere}code{overflow-wrap:anywhere}footer{font-size:13px;color:#53616b;margin-top:24px}
@media(max-width:600px){main{padding:16px 12px}header{padding:18px}.summary div{min-width:50%;padding:12px}section,details{padding:12px}}
'''


def _table(headers: list[str], rows: list[list], caption: str) -> str:
    head = ''.join(f'<th scope="col">{escape(str(h))}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{escape(str(c))}</td>' for c in row) + '</tr>' for row in rows)
    return f'<div class="scroll"><table><caption>{escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_table(report: dict) -> str:
    headers = ['Event', 'Product', *[LABELS[k] for k in COUNT_KEYS]]
    lines = [' | '.join(headers)]
    for entry in report['entries']:
        lines.append(' | '.join(map(str, [entry['event_id'], entry['data_id'], *[entry['counts'][k] for k in COUNT_KEYS]])))
    lines.append(f"Checks: {report['checks_performed']}/{report['verification_budget']}; omitted entries: {report['omitted_entries']}")
    lines.append('Read-only; no network retries. Upstream retention policy: unknown.')
    return '\n'.join(lines) + '\n'


def _entry_html(entry: dict) -> str:
    title = f"{entry['event_id']} · {entry['data_id']}"
    days = [[day['day'], *[day['counts'][k] for k in COUNT_KEYS]] for day in entry['days']]
    checks = [[s['data_time'], s['state'], s['present'], s['size_verified'], s['checksum_verified'], s['usable']] for s in entry['slots']]
    gaps = [[g['start_time'], g['end_time'], g['count']] for g in entry['missing_intervals']]
    attempts = [[a['data_id'], a['data_time'], a['attempted_at'], a['category'], a['http_status'], a['record_index']] for a in entry['source_attempts']]
    extra = [[a['data_time'], a['record_count']] for a in entry['extra_records']]
    return ('<details><summary>' + escape(title) + '</summary>'
        + f'<p class="meta">Metadata: {escape(entry["metadata_state"])}; {escape(entry["units"])}; {escape(entry["crs"])}; cadence {entry["cadence_minutes"]} min.</p>'
        + _table(['Day', *[LABELS[k] for k in COUNT_KEYS]], days, 'Daily coverage in the reporting timezone')
        + _table(['Start (UTC)', 'End (UTC)', 'Slots'], gaps, 'Confirmed missing intervals; unknown and unchecked frames are separate')
        + _table(['Target (UTC)', 'State', 'Present', 'Size', 'SHA-256', 'Usable'], checks, 'Per-slot structural checks')
        + _table(['Observation time (UTC)', 'Records'], extra, 'Outside-window or off-cadence records; excluded from coverage counts')
        + _table(['Product', 'Target (UTC)', 'Attempted (UTC)', 'Category', 'HTTP', 'Record index'], attempts, 'Recorded source attempts; a tested 404 does not establish retention policy')
        + '</details>')


def render_html(report: dict) -> str:
    checksum = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    totals = ''.join(f'<div><dt>{LABELS[k]}</dt><dd>{report["totals"][k]}</dd></div>' for k in COUNT_KEYS)
    rows = [[e['event_id'], e['data_id'], *[e['counts'][k] for k in COUNT_KEYS]] for e in report['entries']]
    overview = _table(['Event', 'Product', *[LABELS[k] for k in COUNT_KEYS]], rows, 'Coverage counts are scheduled slots, not artifact-list lengths')
    entries = ''.join(_entry_html(e) for e in report['entries'])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'sha256-{checksum}'; base-uri 'none'; form-action 'none'">
<title>Archive coverage · MinxiongHydroCast</title><style>{STYLE}</style></head>
<body><header><h1>Archive coverage</h1><p>MinxiongHydroCast · preserved radar / QPE archives</p></header><main>
<div class="notice">Read-only research snapshot. Structural usability does not establish forecast readiness. No network requests or retries.</div>
<dl class="summary">{totals}</dl><p class="meta">Reporting timezone: {escape(report['reporting_timezone'])}. Checks: {report['checks_performed']}/{report['verification_budget']}. Omitted event/product entries: {report['omitted_entries']}.</p>
<section><h2>Event and product overview</h2>{overview}</section><h2>Inspect events, gaps and source attempts</h2>{entries}
<section><h2>Provenance and interpretation</h2><p class="meta">Input type: {escape(report['input_kind'])}<br>Input SHA-256: <code>{escape(report['input_sha256'])}</code></p>
<p>Present, size-verified, checksum-verified and usable are distinct checks. Duplicate timestamps cannot be usable. Unchecked or unknown metadata is not counted as confirmed missing.</p><p>Missing gauge/QPE coverage is not inferred from a radar schedule. Recorded source attempts retain product and timestamps; their retention policy remains unknown. No optional reacquisition plan is executed.</p></section>
<footer>Standalone offline report. Source paths, URLs, keys and original error messages are omitted. Share only with appropriate access.</footer></main></body></html>'''


def write_coverage(report: dict, output: Path, *, root: Path | None, format_name: str) -> None:
    suffixes = {'json': '.json', 'table': '.txt', 'html': '.html'}
    if output.suffix != suffixes.get(format_name):
        raise ValueError('output suffix must match the coverage format')
    if format_name == 'json':
        content = json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n'
    else:
        content = render_html(report) if format_name == 'html' else render_table(report)
    write_new_report(content.encode(), output, root=root)
