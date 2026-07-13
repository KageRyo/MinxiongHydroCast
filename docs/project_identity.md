# Project identity

## Name

**MinxiongHydroCast** is the canonical project and product name.

- **Minxiong** identifies the operational target: Minxiong Township, Chiayi County.
- **Hydro** covers the water-related chain represented in the repository: rainfall, rainfall
  warnings, flood-depth observations, drainage context, and future flood-risk features.
- **Cast** describes the research direction toward short-horizon rainfall nowcasting. It does not
  imply that every current API response is a forecast or that the project issues official warnings.

The name intentionally does not use a general weather term. Temperature, wind, air quality,
typhoon-track prediction, and broad public weather forecasting are outside the current product
contract.

## Technical identifiers

| Surface | Identifier |
| --- | --- |
| Brand and repository | `MinxiongHydroCast` |
| Python distribution | `minxiong-hydrocast` |
| Python import package | `minxionghydrocast` |
| Command prefix | `minxiong-hydrocast-` |
| systemd and runtime prefix | `minxiong-hydrocast-` |
| Environment prefix | `MINXIONGHYDROCAST_` |
| Prometheus metric prefix | `minxionghydrocast_` |

New code and documentation must use these identifiers consistently. Source-authority names such as
CWA and WRA, official upstream dataset IDs, and geographic labels retain their original names.

## Claims vocabulary

Use the following terms according to evidence level:

| Term | Allowed use |
| --- | --- |
| **Official-source observation** | Validated data collected from CWA or WRA with provenance |
| **Operational observation service** | The supervised read API, snapshots, readiness, and metrics |
| **Rainfall nowcast** | Experimental model output that passed its documented model gates |
| **Flood-risk feature** | Derived input or experimental score; never an observed flood fact |
| **Official warning** | Only a warning issued by the responsible government authority |

Do not describe MinxiongHydroCast as an official warning system, guaranteed flood predictor, or
general weather forecast service. Experimental outputs must remain visually and semantically
separate from official warnings and observations.
