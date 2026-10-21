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
HTML_LABELS = {
    'expected': '預期時段', 'present': '檔案存在', 'size_verified': '大小相符',
    'checksum_verified': 'SHA-256 相符', 'usable': '結構可用', 'missing': '確認缺漏',
    'duplicates': '時間重複', 'unchecked': '待檢查',
}
STATE_LABELS = {
    'usable': '結構可用', 'uncaptured': '未收錄', 'file_missing': '檔案不存在',
    'not_checked': '待檢查', 'metadata_invalid': '中繼資料無效',
    'duplicate_timestamp': '時間重複', 'byte_mismatch': '檔案大小不符',
    'checksum_missing': '未提供校驗碼', 'checksum_mismatch': '校驗碼不符',
    'product_changed': '產品不同', 'units_changed': '單位不同',
    'time_mismatch': '觀測時間不符', 'invalid_grid': '網格無效',
    'datum_changed': '座標基準不同', 'all_nodata': '全為無效值',
    'invalid_source': '來源格式無效', 'path_escape': '來源路徑超出範圍',
    'read_error': '檔案無法讀取', 'grid_changed': '網格改變',
    'authentication': '認證失敗', 'rate_limit': '請求受限',
    'http_not_found': '來源不存在', 'transport': '連線失敗',
    'http_other': '其他 HTTP 回應', 'unknown': '未知',
}
STYLE = '''
:root{font:16px/1.6 "Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;color:#203340;background:#f1f5f7;color-scheme:light;--line:#cbd8df;--blue:#17658b;--muted:#506575}
*{box-sizing:border-box}body{margin:0;min-width:320px}header{background:#163e54;color:white;padding:18px max(20px,calc((100vw - 1320px)/2));display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}h1{font-size:23px;margin:0}header p{margin:0;color:#d4e5ee;font-size:14px}main{max-width:1360px;margin:auto;padding:20px 20px 48px}h2{font-size:19px;margin:0 0 10px}.notice{color:var(--muted);font-size:14px;margin:0 0 18px;max-width:80ch}.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:white;border-block:1px solid var(--line);margin:0 0 10px}.summary div{padding:16px 20px}.summary dt{color:var(--muted);font-size:14px}.summary dd{margin:4px 0 0;font-weight:650;font-size:30px;font-variant-numeric:tabular-nums}.summary .warning dd{color:#875300}section{background:white;border:1px solid var(--line);padding:18px;margin:24px 0}details{border-bottom:1px solid var(--line);padding:12px 0;margin:8px 0}details[open]{padding-bottom:20px}summary{cursor:pointer;font-weight:600;min-height:44px;display:list-item;align-content:center;overflow-wrap:anywhere}:focus-visible{outline:3px solid var(--blue);outline-offset:3px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}caption{text-align:left;color:var(--muted);margin:8px 0}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid #dfe7ec;white-space:nowrap}thead{background:#eaf1f5}th{font-weight:600}.meta{font-size:14px;color:var(--muted);overflow-wrap:anywhere}code{overflow-wrap:anywhere}.interpretation p{max-width:80ch}footer{font-size:13px;color:var(--muted);margin-top:24px}
@media(max-width:600px){main{padding:16px 12px}header{padding:14px 16px;gap:2px}.summary{grid-template-columns:1fr 1fr}.summary div{padding:12px 16px}section{padding:12px}}
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


def _state_label(value: str) -> str:
    label = STATE_LABELS.get(value)
    return f'{label} ({value})' if label else value


def _flag(value: bool | None) -> str:
    return '是' if value is True else '否' if value is False else '未知'


def _check_label(slot: dict, key: str) -> str:
    if slot['state'] in ('not_checked', 'metadata_invalid'):
        return '待檢查'
    if key != 'usable' and not slot[key] and any(
        artifact['state'] == 'not_checked' for artifact in slot.get('artifacts', [])
    ):
        return '待檢查'
    return _flag(slot[key])


def _entry_html(entry: dict) -> str:
    title = f"{entry['event_id']} · {entry['data_id']}"
    days = [[day['day'], *[day['counts'][k] for k in COUNT_KEYS]] for day in entry['days']]
    checks = [[s['data_time'], _state_label(s['state']), _flag(s['present']),
               *[_check_label(s, k) for k in ('size_verified', 'checksum_verified', 'usable')]]
              for s in entry['slots']]
    gaps = [[g['start_time'], g['end_time'], g['count']] for g in entry['missing_intervals']]
    attempts = [[a['data_id'], a['data_time'], a['attempted_at'], _state_label(a['category']), a['http_status'], a['record_index']] for a in entry['source_attempts']]
    extra = [[a['data_time'], a['record_count']] for a in entry['extra_records']]
    counts = entry['counts']
    return ('<details><summary>' + escape(title)
        + f' — 缺漏 {counts["missing"]}；待檢查 {counts["unchecked"]}</summary>'
        + f'<p class="meta">中繼資料：{escape(entry["metadata_state"])}；單位 {escape(entry["units"])}；座標 {escape(entry["crs"])}；間隔 {entry["cadence_minutes"]} 分鐘。</p>'
        + _table(['起始時間 (UTC)', '結束時間 (UTC)', '時段數'], gaps, '確認缺漏區間；不含未知或待檢查時段')
        + _table(['日期', *[HTML_LABELS[k] for k in COUNT_KEYS]], days, '依報告時區統計每日覆蓋率')
        + _table(['觀測時間 (UTC)', '判定', '檔案存在', '大小相符', 'SHA-256 相符', '結構可用'], checks, '逐時段檢查；結構可用不等於預報可發布')
        + _table(['觀測時間 (UTC)', '紀錄數'], extra, '範圍外或不符合間隔的紀錄；不計入覆蓋率')
        + _table(['產品', '觀測時間 (UTC)', '嘗試時間 (UTC)', '結果', 'HTTP', '紀錄索引'], attempts, '已記錄的來源請求；404 不代表已知上游保存政策')
        + '</details>')


def render_html(report: dict) -> str:
    checksum = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    totals = ''.join(
        f'<div class="{("warning" if k in ("missing", "unchecked") and report["totals"][k] else "")}">'
        f'<dt>{HTML_LABELS[k]}</dt><dd>{report["totals"][k]}</dd></div>'
        for k in ('expected', 'usable', 'missing', 'unchecked'))
    overview_keys = ('expected', 'usable', 'missing', 'unchecked', 'duplicates')
    rows = [[e['event_id'], e['data_id'], *[e['counts'][k] for k in overview_keys]] for e in report['entries']]
    overview = _table(['事件', '產品', *[HTML_LABELS[k] for k in overview_keys]], rows, '以預定觀測時段統計；可展開事件查看缺漏時間與檢查結果')
    integrity_keys = ('present', 'size_verified', 'checksum_verified', 'duplicates')
    integrity = _table([HTML_LABELS[k] for k in integrity_keys],
                       [[report['totals'][k] for k in integrity_keys]], '各項檢查獨立計數，不應相加')
    entries = ''.join(_entry_html(e) for e in report['entries'])
    demo_notice = '合成示範資料。' if report.get('demo') else ''
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'sha256-{checksum}'; base-uri 'none'; form-action 'none'">
<title>資料覆蓋率 · MinxiongHydroCast</title><style>{STYLE}</style></head>
<body><header><h1>資料覆蓋率</h1><p>MinxiongHydroCast 雷達與 QPE 封存資料</p></header><main>
<p class="notice">{demo_notice}離線研究快照。結構可用僅表示通過資料檢查，不代表預報已達發布條件。</p>
<dl class="summary">{totals}</dl>
<p class="meta">已執行 {report['checks_performed']} 次檔案檢查，本次上限 {report['verification_budget']} 次。尚未檢查的時段不代表缺漏或不合格。</p>
<p class="meta">報告時區：{escape(report['reporting_timezone'])}。因輸出上限省略 {report['omitted_entries']} 組事件／產品。</p>
<section><h2>事件與產品</h2>{overview}</section><h2>缺漏區間與檢查結果</h2>{entries}
<details><summary>完整性檢查明細</summary>{integrity}</details>
<details class="interpretation"><summary>資料來源與判讀方式</summary><p class="meta">輸入類型：{escape(report['input_kind'])}<br>輸入 SHA-256：<code>{escape(report['input_sha256'])}</code></p>
<p>檔案存在、大小相符、校驗碼相符與結構可用是不同檢查。時間重複的紀錄不可判定為可用；未檢查或中繼資料未知的時段，不計為確認缺漏。</p><p>雨量站與 QPE 的缺漏不從雷達排程推算。上游保存政策仍未知，本報告不執行網路請求、重試或補抓。</p></details>
<footer>本報告可獨立離線開啟。未包含來源路徑、網址、金鑰或原始錯誤訊息；分享前請確認資料存取權限。</footer></main></body></html>'''


def write_coverage(report: dict, output: Path, *, root: Path | None, format_name: str) -> None:
    suffixes = {'json': '.json', 'table': '.txt', 'html': '.html'}
    if output.suffix != suffixes.get(format_name):
        raise ValueError('output suffix must match the coverage format')
    if format_name == 'json':
        content = json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n'
    else:
        content = render_html(report) if format_name == 'html' else render_table(report)
    write_new_report(content.encode(), output, root=root)
