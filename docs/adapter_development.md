# Data-source adapter development

Operational adapters provide one public, fail-closed interface:

```python
class SourceAdapter(Protocol):
    source_id: str
    adapter_version: str
    dataset: str

    def collect(self) -> SourceResult:
        ...
```

`collect()` is an atomic fetch-and-validate transaction. A successful result carries normalized
records, source outcome, authority, dataset ID, redacted URL, fetch time, adapter/schema version,
content SHA-256, and bounded retry metrics. Keeping fetch and validation atomic prevents callers
from accidentally publishing an unvalidated raw capture.

## Required invariants

- `source_id` is the authority's stable dataset ID and matches
  `result.provenance.dataset_id`.
- `adapter_version` identifies the adapter/schema contract and matches
  `result.provenance.schema_version`.
- `dataset` is the stable MinxiongHydroCast product name and matches `result.dataset`.
- `fetched_at` is a timezone-aware ISO-8601 timestamp with source provenance.
- `content_sha256` hashes the raw response bytes or a documented canonical transaction.
- schema drift raises `SourceSchemaError` and never activates a scraper fallback.
- transport/authentication/rate-limit failures raise `SourceRequestError`; only those failures may
  use an explicitly degraded fallback.
- valid empty products use `outcome=empty` only where the product contract permits it.
- stale products use `outcome=stale` and cannot satisfy operational readiness.

## Contract test

Use a deterministic fixture transport; do not call an authority in the ordinary unit test suite.

```python
result = adapter.collect()
validate_adapter_contract(adapter, result)

assert result.provenance.authority
assert result.provenance.fetched_at
assert result.provenance.content_sha256
```

Also test missing credentials, HTTP failure, malformed JSON, unknown/missing fields, unexpected
empty results, invalid units/timestamps, stale observations, and secret redaction. Scheduled live
contract checks belong in `.github/workflows/cwa-live-contract.yml` or an equivalently protected
workflow.

## Register an adapter

1. Add the strict raw-response Pydantic models and normalization code under
   `minxionghydrocast.ingestion`.
2. Return a `SourceResult` with complete `SourceProvenance` and retry telemetry.
3. Add deterministic fixture tests plus the shared contract assertion.
4. Document authority, dataset, use, license/terms, retention, and redistribution status in
   [the source register](data_source_register.md).
5. Wire the adapter into collection only after failure and freshness behavior are explicit.
6. Keep any live smoke command under the grouped `mhc source ...` CLI.

An adapter does not by itself make a region, product, forecast, or redistribution path
operationally supported.
