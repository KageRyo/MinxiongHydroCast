"""Self-contained HTML export with script-safe data and exclusive atomic publication."""

import base64
import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any

from minxionghydrocast.research.report_export import write_new_report


def write_replay(payload: dict[str, Any], output: Path, *, root: Path | None = None) -> None:
    output = output.expanduser().resolve()
    if output.suffix != '.html':
        raise ValueError('replay output must be an HTML file')
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    template = files('minxionghydrocast.research').joinpath('replay.html').read_text(encoding='utf-8')
    rendered = template.replace('__REPLAY_DATA__', data)
    for tag, placeholder in [('script', '__SCRIPT_POLICY__'), ('style', '__STYLE_POLICY__')]:
        blocks = re.findall(rf'<{tag}[^>]*>(.*?)</{tag}>', rendered, re.S)
        hashes = [base64.b64encode(hashlib.sha256(block.encode('utf-8')).digest()).decode('ascii')
                  for block in blocks]
        policy = ' '.join(f"'sha256-{checksum}'" for checksum in hashes)
        rendered = rendered.replace(placeholder, policy)
    html = rendered.encode('utf-8')
    write_new_report(html, output, root=root)
