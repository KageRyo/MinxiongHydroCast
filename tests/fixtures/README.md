# Contract Fixtures

`cwa_o_a0002_001.json` is a minimized, credential-free contract fixture derived from the public
CWA `O-A0002-001` response shape. It is not a raw API capture and contains only the fields and two
rows needed to detect upstream schema drift and county-filtering regressions.

`wra_rainfall_warning.json` is a minimized, credential-free fixture for the WRA OpenApiv3
rainfall-warning response. The adapter also tests the observed no-warning response separately as
`{"UpdataTime": null, "Data": []}`.

`wra_iow_latest.json` and `wra_iow_catalog.json` are minimized fixtures for the public WRA IoW
flood-depth measurement and sensor-metadata datasets. They contain only enough rows to exercise
pagination, regional filtering, the `sensorid` join, and schema-drift checks; they are not raw API
archives.
