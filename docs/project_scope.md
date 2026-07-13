# Project scope

## Purpose

MinxiongHydroCast provides a reproducible hydrometeorological data and research foundation for
Minxiong Township. Its immediate product is an internal official-source observation and
data-quality service. Its research track evaluates short-horizon rainfall nowcasting and future
local flood-risk methods without presenting experimental output as public guidance.

## Current supported capabilities

- Collect and validate CWA rain-gauge observations.
- Collect and validate WRA rainfall warnings and IoW flood-depth observations.
- Preserve source provenance, raw-content checksums, schema versions, freshness, and source outcome.
- Publish immutable operational snapshots with explicit health and readiness states.
- Derive a snapshot-aligned Minxiong feature and location-reference contract.
- Expose a localhost operator view, versioned read API, and Prometheus metrics.
- Run supervised collection, monitoring, local alert auditing, backup, restore, and shadow gates.
- Build reproducible radar event datasets and compare rainfall-nowcasting baselines.

## Experimental capabilities

- Radar/QPE tensor construction and gauge validation.
- Persistence and Tiny U-Net rainfall-nowcasting evaluation.
- NowcastNet adapter and migration research.
- Flood-risk feature engineering and label auditing.

Experimental capability does not imply operational availability. `/api/v1/experimental-forecasts`
must remain unavailable until its data, model, shadow, and communication gates pass.

## Non-goals

- General weather forecasting across temperature, wind, humidity, or air quality.
- Issuing or replacing CWA, WRA, NCDR, fire-department, or local-government warnings.
- Claiming street-level inundation solely from rainfall thresholds.
- Training on unreviewed demo labels or evaluating on random frame splits.
- Public network exposure without authentication, TLS, an owner, and an incident path.
- Enabling automated public notifications before model and human-override gates pass.

## Product boundaries

The product surfaces are deliberately separated:

1. **Official warnings:** upstream government products, attributed without reinterpretation.
2. **Official observations:** validated rain-gauge and flood-depth measurements.
3. **Derived operational features:** snapshot-aligned aggregates with explicit upstream health.
4. **Experimental forecasts:** unavailable or clearly marked until every forecast gate passes.

An upstream outage, stale observation, schema drift, missing Minxiong coverage, or scraper fallback
must fail readiness instead of silently substituting a prediction or older product.

## Geographic boundary

Minxiong Township is the operational decision boundary. Chiayi County observations provide local
context, and Taiwan-wide radar data may be used for model training and evaluation. Broader input
coverage does not expand the area for which the service may make operational claims.
