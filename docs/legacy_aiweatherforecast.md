# Legacy AIWeatherForecast Boundary

`AIWeatherForecast` predates the canonical MinxiongHydroCast repository. Its notebooks, one-off
collection scripts, and small local data exports are not imported or executed by the current
MinxiongHydroCast package or deployment templates.

Treat the directory as a read-only migration source until each item has an explicit disposition:

- promote reusable code, safe samples, or documentation into this repository with tests;
- move durable raw or derived assets to the external data root with a catalog entry and checksum;
- retain historical notebooks and exports in a dated archive; or
- delete only files proved to be duplicate, generated, or no longer required.

Do not delete the legacy directory as part of a code-only refactor. Record the inventory and an
approved retention decision before archival or removal. The canonical repository remains
`KageRyo/MinxiongHydroCast`.
