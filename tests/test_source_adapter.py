from minxionghydrocast.ingestion.source_adapter import (
    SourceAdapter,
    SourceProvenance,
    SourceResult,
    records_sha256,
    validate_adapter_contract,
)


class FixtureAdapter:
    dataset = "rain_gauges"
    source_id = "fixture-rain"
    adapter_version = "fixture-rain-v1"

    def collect(self) -> SourceResult:
        records = [{"station": "synthetic"}]
        return SourceResult(
            dataset=self.dataset,
            records=records,
            provenance=SourceProvenance(
                source_kind="demo_fixture",
                outcome="ok",
                authority="MinxiongHydroCast",
                dataset_id=self.source_id,
                source_url="demo://fixture-rain",
                fetched_at="2026-07-31T12:00:00+08:00",
                schema_version=self.adapter_version,
                content_sha256=records_sha256(records),
            ),
        )


def test_public_adapter_contract_accepts_complete_fixture_result():
    adapter = FixtureAdapter()

    result = validate_adapter_contract(adapter, adapter.collect())

    assert isinstance(adapter, SourceAdapter)
    assert result.dataset == "rain_gauges"
    assert result.provenance.content_sha256


def test_public_adapter_contract_rejects_identity_drift():
    adapter = FixtureAdapter()
    result = adapter.collect()
    drifted = SourceResult(
        dataset=result.dataset,
        records=result.records,
        provenance=result.provenance.model_copy(update={"dataset_id": "changed-upstream"}),
    )

    try:
        validate_adapter_contract(adapter, drifted)
    except ValueError as exc:
        assert "source_id must match" in str(exc)
    else:
        raise AssertionError("identity drift must fail the adapter contract")


def test_public_adapter_contract_rejects_naive_fetch_timestamp():
    adapter = FixtureAdapter()
    result = adapter.collect()
    naive = SourceResult(
        dataset=result.dataset,
        records=result.records,
        provenance=result.provenance.model_copy(
            update={"fetched_at": "2026-07-31T12:00:00"}
        ),
    )

    try:
        validate_adapter_contract(adapter, naive)
    except ValueError as exc:
        assert "UTC offset" in str(exc)
    else:
        raise AssertionError("adapter provenance timestamps must be timezone-aware")
