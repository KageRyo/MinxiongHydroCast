# Continuous Event Evidence

`mhc event-discover` continuously preserves short-retention CWA radar events before they disappear.
It is a research-data collector, not a forecast publisher and not an automatic training trigger.

## Collection Cycle

Each successful run:

1. fetches the official `O-A0059-001` history index over verified TLS;
2. scans only frames newer than the persisted cursor, using a 120-minute lookback on first run;
3. computes Minxiong-local and Taiwan-wide coverage at `35 dBZ`;
4. groups qualifying frames into candidate windows and preserves 60 minutes before the first
   trigger and 60 minutes after the latest trigger at the 10-minute source cadence;
5. captures current `O-B0045-001` QPE, `O-A0002-001` Chiayi gauges, and WRA
   `Rainfall/Warning` evidence for the latest trigger of each new or extended candidate;
6. atomically updates the Pydantic-validated `EventEvidenceCatalog` only when source state changes.

The default local threshold is one Minxiong-area pixel at or above `35 dBZ`. The default
Taiwan-wide threshold is 1,000 pixels. Both coverage values are retained for every scanned frame,
including frames that do not create a candidate.

Run one cycle after loading the ignored `.env`:

```bash
set -a
source .env
set +a

mhc event-discover --repository-root "$PWD"
```

## External Layout

All artifacts are under `MINXIONGHYDROCAST_RESEARCH_ROOT`, which must remain outside Git:

```text
research-root/
├── discovery/
│   ├── event_evidence_catalog.json
│   ├── history/
│   ├── frame_metrics/
│   └── scan_cache/
├── raw/event_evidence/<candidate-id>/
├── events/<candidate-id>_{plan,collection}.json
└── evidence/<candidate-id>/<capture-id>/
    ├── O-B0045-001.json
    ├── O-A0002-001.json
    └── WRA-Rainfall-Warning.json
```

Candidate frames, event plans, collection manifests, and synchronized evidence are durable and
cataloged with byte sizes and SHA-256. Interrupted downloads resume from complete atomic files;
checksum-damaged candidate frames are rejected and redownloaded while the CWA history source still
has them. The temporary scan cache alone is pruned, by default after 48 hours or above 10 GiB.

Repeated runs against the same history index do not advance the cursor, create another evidence
capture, rewrite the catalog, or duplicate a candidate. Failed evidence sources remain explicit
`error` records and are retried on later cycles. Each source stores its observation time and its
absolute alignment delta from the radar trigger so a reviewer can identify late or mismatched
evidence. A non-empty source more than 20 minutes from the target is retained as `stale`, not
silently treated as synchronized.

## Human Review Boundary

Discovery always writes:

- `queue=candidate_only`;
- `review_status=pending`;
- `formal_split_membership=not_added`;
- `weather_regime=unclassified`;
- `automatic_formal_split_updates=false` at catalog level.

A complete radar window moves only to `operational_status=awaiting_review`. A reviewer must inspect
the radar frames, source timing, QPE, gauges, warnings, and official synoptic context. Record the
decision through the schema-validated command rather than editing JSON directly:

```bash
mhc event-review \
  --catalog "$MINXIONGHYDROCAST_RESEARCH_ROOT/discovery/event_evidence_catalog.json" \
  --candidate-id <candidate-id> \
  --decision approved \
  --reviewer <reviewer-identity> \
  --weather-regime convective \
  --official-context https://www.cwa.gov.tw/<official-source> \
  --notes "Reviewed radar, QPE, gauges, warnings, and official context."
```

Approval requires a complete window, at least one capture with synchronized QPE/gauge/warning
evidence, a named reviewer, timezone-aware review time, a non-`unclassified` regime, and at least
one official HTTPS context reference. A repeated identical review is idempotent; a conflicting
second decision is rejected. Rejection also requires a complete window and reviewer identity, but
may remain `unclassified` when the candidate is a false positive.

`mhc event-review` still does not edit `data/samples/event_split_manifest.json`. Adding an approved
event is a separate tracked change with an explicit train/validation/test decision. The manifest
event must set `evidence_candidate_id`, use the reviewed window, and match the reviewed weather
regime in `event_type`. Then run:

```bash
mhc event-split-check \
  --manifest data/samples/event_split_manifest.json \
  --event-evidence-catalog \
    "$MINXIONGHYDROCAST_RESEARCH_ROOT/discovery/event_evidence_catalog.json" \
  --require-ok

mhc dataset-build \
  --manifest data/samples/event_split_manifest.json \
  --event-evidence-catalog \
    "$MINXIONGHYDROCAST_RESEARCH_ROOT/discovery/event_evidence_catalog.json" \
  --root "$MINXIONGHYDROCAST_RESEARCH_ROOT"
```

Both commands reject a referenced candidate that is unknown, incomplete, unapproved,
checksum-invalid, time-mismatched, or regime-mismatched. The dataset build applies the same gate
before any download or training.

Retraining is allowed only after newly reviewed events enter the formal manifest. It must rerun the
same independent validation/test comparison and unchanged Persistence promotion gate. Do not tune
against the existing held-out events, loosen the gate, publish the forecast endpoint, or upgrade
NowcastNet as part of event discovery.

## Scheduled Operation

The single-host installer enables `minxiong-hydrocast-event-discover.timer` every 20 minutes. Its
run summary is stored at:

```text
~/.local/share/minxiong-hydrocast/run_summaries/event_discover.json
```

Inspect it without exposing credentials:

```bash
systemctl --user status minxiong-hydrocast-event-discover.timer
systemctl --user status minxiong-hydrocast-event-discover.service
journalctl --user -u minxiong-hydrocast-event-discover.service
```

## Deployed Status And Next Task

The managed single-host profile installed this timer from `main` revision `7f8fccc` on
2026-07-14. The installed revision matched Git, the first service run succeeded, and subsequent
20-minute runs continued advancing the same candidate without editing the formal split.

The 12:00 catalog snapshot had one active `collecting` candidate with 82 of 88 frames, 76 triggers,
18 synchronized `ok/ok/empty` QPE/gauge/warning captures, and zero artifact-verification errors.
It remained `review_status=pending`, `weather_regime=unclassified`, and
`formal_split_membership=not_added`. See [deployment_status.md](deployment_status.md) for the dated
evidence; inspect the live catalog for current counts because an active event can keep extending
its window.

The next task is data curation, not model tuning:

1. wait until the rolling post-trigger window is complete and the candidate reaches
   `operational_status=awaiting_review`;
2. inspect its radar frames, synchronized evidence timing, and an official CWA/WRA weather-context
   source;
3. record an approved or rejected `mhc event-review` decision without changing the formal split;
4. repeat this process until reviewed typhoon, frontal, Mei-yu, and convective regimes are
   represented;
5. only then propose a tracked split change, rebuild the dataset, retrain, and rerun the unchanged
   Persistence promotion gate.

Accumulating all target weather regimes is an ongoing observational requirement. The collector can
preserve and classify future evidence, but no regime should be claimed until a human review attaches
official weather context.
