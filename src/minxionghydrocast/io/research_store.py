"""Compatibility imports for the former external research-store module.

The durable root now represents data assets rather than a separate research project. New code
should import from :mod:`minxionghydrocast.io.data_store`.
"""

from minxionghydrocast.io.data_store import (
    DataLayout,
    DataLockError,
    ResearchLayout,
    ResearchLockError,
    artifact_record,
    atomic_write_bytes,
    atomic_write_schema,
    canonical_json_bytes,
    prune_cache,
    require_external_data_root,
    require_external_research_root,
    sha256_file,
    write_schema_if_changed,
)

__all__ = [
    "DataLayout",
    "DataLockError",
    "ResearchLayout",
    "ResearchLockError",
    "artifact_record",
    "atomic_write_bytes",
    "atomic_write_schema",
    "canonical_json_bytes",
    "prune_cache",
    "require_external_data_root",
    "require_external_research_root",
    "sha256_file",
    "write_schema_if_changed",
]
