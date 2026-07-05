# Radar Data Sources

FloodCastTW cannot train a Taiwan-specific nowcasting model until source radar data is confirmed.
This repository tracks candidates with a manifest instead of committing raw radar files.

## Manifest

The sample manifest is `data/samples/radar_source_manifest.json`. It records:

- provider and source URLs
- license and license URL
- access method
- native format
- cadence
- projection / CRS
- grid description
- units
- local ignored storage path

The current sample is intentionally marked `candidate`; it is not ready for training.

## Check Command

```bash
floodcasttw-radar-source-check \
  --manifest data/samples/radar_source_manifest.json \
  --output data/processed/radar_source_check.json
```

Use `--require-confirmed` in automation when training should fail unless the selected source is
fully reviewed:

```bash
floodcasttw-radar-source-check --require-confirmed
```

The command writes a JSON result and the standard run summary/log files.

## Confirmation Criteria

Before tensor conversion or training, the selected source must have:

- `status` set to `confirmed`
- known native file format
- cadence in minutes
- CRS / projection
- grid geometry or enough metadata to derive it
- rainfall or reflectivity units
- reviewed license and attribution requirements
- local storage path outside git

After confirmation, update the radar tensor contract if the source does not match the provisional
`512 x 512`, 6-minute, `mm_per_hour`, `EPSG:4326` adapter spec.
