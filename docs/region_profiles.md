# Region profiles

Minxiong remains the reference implementation, while a strict region profile moves the
operational boundary out of collector code. Select it with:

```bash
mhc collect --region minxiong --mode demo --once
```

Profiles are packaged under `src/minxionghydrocast/profiles/`. They use JSON-compatible YAML, a
strict subset of YAML, so the base installation stays dependency-light. Unknown fields, invalid
authority codes, path traversal, non-positive freshness limits, and unknown timezones are
rejected.

Each profile declares:

- stable region ID, display name, official county/township names and codes, and timezone;
- minimum rain-gauge and enabled flood-sensor coverage;
- a packaged GeoJSON working boundary and radar-grid contract ID;
- independent rain-gauge and flood-sensor freshness limits.

`example-region.yaml` is a schema example, not supported live configuration. Before proposing a
new region, replace its placeholder boundary, verify exact authority identifiers, add fixture and
live-contract evidence, and document any source or redistribution differences. Adding a profile
does not expand forecast publication or operational support automatically.
