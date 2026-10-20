"""Self-contained HTML export with script-safe data and exclusive atomic publication."""

import json
import os
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from minxionghydrocast.io.data_store import DataLayout, require_external_data_root


def write_replay(payload: dict[str, Any], output: Path, *, root: Path | None = None) -> None:
    output = output.expanduser().resolve()
    roots = [Path(tempfile.gettempdir()).resolve()]
    if root is not None:
        roots.append(root.expanduser().resolve())
    if output.suffix != '.html' or not any(output.is_relative_to(p) for p in roots):
        raise ValueError('replay output must be a new HTML file inside the data or temporary root')
    require_external_data_root(DataLayout(output.parent), repository_root=Path(__file__).resolve().parents[3])
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    template = files('minxionghydrocast.research').joinpath('replay.html').read_text(encoding='utf-8')
    html = template.replace('__REPLAY_DATA__', data).encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(html)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)  # Atomic publication; never replaces existing files.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
