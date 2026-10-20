"""Export a standalone offline radar event replay explorer."""

import argparse
from pathlib import Path

from minxionghydrocast.research.replay import build_replay
from minxionghydrocast.research.replay_demo import build_demo
from minxionghydrocast.research.replay_export import write_replay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--root', type=Path, help='External data root with verified backtest artifacts.')
    source.add_argument('--demo', action='store_true', help='Generate a credential-free synthetic replay.')
    parser.add_argument('--report', type=Path, default=Path('backtests/latest.json'))
    parser.add_argument('--context', type=Path, help='Optional checksum-pinned hourly QPE/gauge manifest.')
    parser.add_argument('--output', type=Path, required=True, help='New HTML file in data or temporary root.')
    parser.add_argument('--preview-size', type=int, default=160)
    parser.add_argument('--max-frames', type=int, default=120)
    parser.add_argument('--max-windows', type=int, default=24)
    args = parser.parse_args()
    limits = {key: getattr(args, key) for key in ('preview_size', 'max_frames', 'max_windows')}
    try:
        payload = build_demo(**limits) if args.demo else build_replay(
            root=args.root, report_path=args.report, context_path=args.context, **limits)
        write_replay(payload, args.output, root=args.root)
    except (OSError, ValueError):
        parser.exit(2, 'Replay export failed: verify inputs, limits and a new permitted HTML destination.\n')
    print('[OK] offline replay exported; open the HTML file in a browser.')


if __name__ == '__main__':
    main()
