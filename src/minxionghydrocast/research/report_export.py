"""Exclusive atomic publication of new external research report files."""

import os
import tempfile
from pathlib import Path

from minxionghydrocast.io.data_store import DataLayout, require_external_data_root


def write_new_report(payload: bytes, output: Path, *, root: Path | None = None) -> None:
    output = output.expanduser().resolve()
    roots = [Path(tempfile.gettempdir()).resolve()]
    if root is not None:
        roots.append(root.expanduser().resolve())
    if not any(output.is_relative_to(p) for p in roots):
        raise ValueError('report destination must remain in the data or temporary root')
    require_external_data_root(DataLayout(output.parent), repository_root=Path(__file__).resolve().parents[3])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
