# Deployment status

This page records dated, public-safe evidence from a private localhost-only shadow deployment. It
does not publish hostnames, mount paths, runner identities, notification destinations, raw
snapshots, backup digests, candidate identifiers, or unpublished data artifacts.

It also does not claim that MinxiongHydroCast is an official warning system or authorize external
operational use. Runtime state remains the authority; this page is a release-oriented snapshot.

## Verified on 2026-07-29

The latest live observation attempt was healthy and ready:

- WRA active rainfall warnings: a strictly validated empty official product;
- CWA rain gauges: 80 Chiayi County records;
- WRA IoW flood sensors: 150 joined measurement/catalog records;
- derived location reference: 230 rows;
- Minxiong feature contract: one ready row;
- per-source retry count: zero for the clean attempt.

The API health endpoint returned HTTP 200, readiness returned HTTP 200, and the operator view
loaded without browser console errors. API source URLs redacted credentials. The real operator view
used in the release README shows both the healthy live snapshot and the blocked shadow gate.

## Rolling shadow evidence

The 192-hour report evaluated through 2026-07-29 13:00 Asia/Taipei:

| Metric | Result | Required | Check |
| --- | ---: | ---: | --- |
| Duration | 191.85 hours | at least 168 hours | Pass |
| Live attempts | 1,150 | at least 900 | Pass |
| Collection success | 99.3913% | at least 99% | Pass |
| Readiness | 97.3913% | at least 95% | Pass |
| Maximum ready-data gap | 50.983 minutes | at most 30 minutes | **Fail** |
| Confirmed and covered heavy-rain periods | 0 | at least 1 | **Fail** |
| Storage integrity | valid | valid | Pass |
| Evidence contract | valid | valid | Pass |

The old reliability failures remain in the rolling evidence and are not deleted. The gate can pass
only after the window naturally excludes old gaps and a real, reviewed heavy-rain period has
continuous ready coverage. `notification_allowed=false`.

## Reliability rollout

The WRA reliability work is deployed in the private shadow environment:

- bounded retries cover empty response bodies, invalid JSON, malformed pages, and exact repeated
  pagination payloads;
- repeated malformed payloads remain visible as schema drift;
- the full flood measurement/catalog join transaction is retried a bounded number of times when
  the two official products change during collection;
- retry source, reason, and count are persisted in run summaries, snapshot manifests, API status,
  and Prometheus metrics;
- strict schemas, freshness, joins, and fail-closed behavior were not weakened.

Post-rollout official-source contract checks returned a healthy empty warning product, CWA gauge
observations, and WRA flood-sensor observations. Backup creation and independent archive
verification completed successfully.

## WRA freshness incident evidence — 2026-09-12

The scheduled `Official Live Contracts` run observed a valid WRA IoW response with 150 joined
records, while the CWA rain-gauge contract completed successfully. The WRA response was classified
as `stale` because its newest observation remained at 2026-09-02 12:25 Asia/Taipei when fetched on
2026-09-12. Repeated local captures had the same upstream content checksum while their fetch times
advanced, which is consistent with an unchanged upstream snapshot rather than a parser crash or
missing credential.

The WRA catalog describes IoW flood-depth data as an approximately hourly public snapshot. The
90-minute freshness limit is therefore retained: widening it to make the scheduled check green
would hide a source-cadence failure and weaken readiness semantics. See
[WRA freshness evidence](wra_freshness_evidence.md) for the measurement and follow-up procedure.

## Data and publication state

Continuous event discovery and the read-only review queue remain active in the private external
data root. Candidate ranking does not edit review decisions or formal event splits. Raw radar,
QPE, gauges, warning captures, official-context artifacts, and candidate-level evidence are not
published by this status page.

The formal public benchmark remains the five-event CWA split documented in
[baseline results](baseline_results.md). Weighted Tiny U-Net improves aggregate RMSE on the
independent validation and two local test events, but it regresses CSI on one local test event and
some lead-time metrics. The latest private review-queue aggregate contains 128 candidates: 1
approved `convective`, 2 rejected/unclassified, and 125 pending. No `typhoon`, `frontal`, or
`mei_yu` candidate is approved, and all candidate formal-split memberships remain `not_added`.
`forecast_publication_ready=false`.

## Active blockers

- Observe a rolling maximum ready-data gap of at most 30 minutes.
- Review and cover at least one real confirmed heavy-rain period.
- Accumulate meaningful typhoon, frontal, Mei-yu, and convective event diversity.
- Complete historical QPE/gauge validation.
- Review at least 10 positive and 20 negative local flood labels.
- Assign external notification and incident ownership before activating a human channel.
- Add authenticated TLS ingress and remote backup only if the localhost service is intentionally
  made network-accessible.

Automated risk notification, external operational use, and forecast publication remain disabled.

## Recording policy

- `docs/tasks.md` owns current work.
- `docs/roadmap.md` owns long-term direction.
- Run summaries own changing attempt counts, rates, gaps, and artifact verification.
- This file may record aggregate, dated release evidence only.
- Hostnames, absolute deployment paths, runner names, internal ports beyond generic runbook
  examples, secrets, recipient identities, raw data, and unpublished candidate evidence stay
  private.
