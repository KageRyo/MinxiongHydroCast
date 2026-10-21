"""Report preserved archive coverage and quality without acquisition or mutation."""

import argparse
import json
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from minxionghydrocast.research.archive_coverage import build_coverage
from minxionghydrocast.research.coverage_demo import build_coverage_demo
from minxionghydrocast.research.coverage_view import render_table, write_coverage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--root', type=Path, help='External data root.')
    source.add_argument('--demo', action='store_true', help='Credential-free synthetic coverage example.')
    parser.add_argument('--catalog', type=Path, default=Path('discovery/event_evidence_catalog.json'))
    parser.add_argument('--max-checks', type=int, default=250, help='Maximum raw-frame verification attempts (0..10000).')
    parser.add_argument('--max-entries', type=int, default=10)
    parser.add_argument('--timezone', default='Asia/Taipei')
    parser.add_argument('--format', choices=['json', 'table', 'html'], default='json')
    parser.add_argument('--output', type=Path, help='New .json/.txt/.html file below data or system temp root.')
    args = parser.parse_args()
    if args.format == 'html' and args.output is None:
        parser.error('HTML format requires --output')
    options = {'max_checks': args.max_checks, 'max_entries': args.max_entries, 'timezone': args.timezone}
    try:
        report = build_coverage_demo(**options) if args.demo else build_coverage(
            root=args.root, catalog_path=args.catalog, **options)
        if args.output is not None:
            write_coverage(report, args.output, root=args.root, format_name=args.format)
            print('[OK] archive coverage exported; source artifacts were not changed.')
        elif args.format == 'json':
            print(json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False))
        else:
            print(render_table(report), end='')
    except (OSError, ValueError, ZoneInfoNotFoundError):
        parser.exit(2, 'Coverage report failed: verify catalog metadata, limits, timezone and a new permitted output.\n')


if __name__ == '__main__':
    main()
