# Continuous Event Evidence

`mhc event-discover` continuously preserves short-retention CWA radar events before they disappear.
It is a research-data collector, not a forecast publisher and not an automatic training trigger.

## Collection Cycle

Each successful run:

1. fetches the official `O-A0059-001` history index over verified TLS;
2. scans only frames newer than the persisted cursor, using a 120-minute lookback on first run;
3. computes Minxiong-local and Taiwan-wide coverage at `35 dBZ`;
4. persists both coverage metrics, but groups only Minxiong-local qualifying frames into candidate
   windows and preserves 60 minutes before the first local trigger and 60 minutes after the latest
   local trigger at the 10-minute source cadence, with a 480-minute maximum total window;
5. captures current `O-B0045-001` QPE, `O-A0002-001` Chiayi gauges, and WRA
   `Rainfall/Warning` evidence for the latest trigger of each new or extended candidate;
6. atomically updates the Pydantic-validated `EventEvidenceCatalog` only when source state changes.

The default local threshold is one Minxiong-area pixel at or above `35 dBZ`. The default
Taiwan-wide threshold is 1,000 pixels. `minxiong_35dbz` is the fixed review-queue trigger;
`taiwan_wide_35dbz` is context only. Both coverage values and labels are retained under
`discovery/frame_metrics/` for every scanned frame, including Taiwan-wide-only frames that do not
create or extend a candidate.

The maximum covers the complete window, including its before/after context. With the defaults, one
candidate can therefore contain at most six hours between its first and last trigger. A qualifying
frame that would exceed the limit starts a new candidate, while the preceding candidate retains
its original identifier and evidence. Context at a boundary may overlap; formal split curation
must keep overlapping candidate windows out of independent train, validation, and test splits.
Catalogs written before this setting was introduced parse with the 480-minute default. If an
existing candidate is already longer, its window remains unchanged, and the next qualifying frame
starts a new candidate.

Run one cycle after loading the ignored `.env`:

```bash
set -a
source .env
set +a

mhc event-discover --repository-root "$PWD"
```

Use `--max-candidate-window-minutes` to select another cadence-aligned bound. It must cover at least
the configured before/after context. Changing the bound affects future trigger grouping, so do not
change it while a candidate is collecting without an explicit catalog rollout decision.

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
└── evidence/<candidate-id>/
    ├── <capture-id>/
    │   ├── O-B0045-001.json
    │   ├── O-A0002-001.json
    │   └── WRA-Rainfall-Warning.json
    └── official_context/
        └── <index>_<sha256-prefix>_<source-name>
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

The structured run summary reports `trigger_frames` as Minxiong-local candidate triggers and
`context_trigger_frames` as all frames carrying either the local or Taiwan-wide context label.
This keeps queue growth observable without discarding broader radar conditions.

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
  --official-context-file /path/to/captured-official-report.pdf \
  --official-context-publisher "Central Weather Administration, Taiwan" \
  --official-context-published-at 2026-07-14T11:00:00+08:00 \
  --notes "Reviewed radar, QPE, gauges, warnings, and official context."
```

Approval requires a complete window, at least one capture with synchronized QPE/gauge/warning
evidence, a named reviewer, timezone-aware review time, a non-`unclassified` regime, and at least
one official HTTPS context reference paired with a non-empty local file, publisher, and
timezone-aware publication time. Repeat all four options in the same order for multiple sources.
The command records its fetch time, atomically copies each file under the candidate evidence
directory, and catalogs its relative path, byte size, and SHA-256. The shared catalog verifier
therefore rejects missing or modified official context just like damaged radar/QPE/gauge/warning
evidence. A repeated identical review is idempotent; a conflicting second decision is rejected.
Rejection also requires a complete window and reviewer identity, but may remain `unclassified`
when the candidate is a false positive.

Catalogs containing earlier URL-only review records remain readable. New approval decisions require
the checksummed artifact fields and must not treat a mutable web URL as permanent evidence.

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

## Validated Operation

The managed single-host profile runs this timer every 20 minutes with a 480-minute maximum total
candidate window. The first overlong pre-bound candidate retained its existing window while the
first later qualifying frame started a second candidate, confirming that rollout does not rewrite
previously cataloged evidence.

The first candidate completed with 116 of 116 radar frames, 104 qualifying triggers, and 32
synchronized `ok/ok/empty` QPE/gauge/warning captures. A checksummed CWA W01 report supported its
`approved/convective` review. The local evidence was weak: one Minxiong-local 37.8 dBZ trigger,
0.5 mm peak QPE at the configured point, zero one-hour rain at the four latest Minxiong gauges, and
no active WRA warning. The decision therefore records a reviewable convective radar candidate, not
a flood or warning event. Full artifact verification passed, a repeated identical review was
idempotent, and formal membership remained `not_added`. See
[deployment_status.md](deployment_status.md) for the dated evidence.

Two later complete windows contained six Taiwan-wide triggers each but no Minxiong-local trigger.
Their synchronized QPE/gauge/warning captures were respectively four and three sets of
`ok/ok/empty`, with no Minxiong rain or active WRA warning evidence. Human review therefore
recorded both as `rejected/unclassified` for the Minxiong-local queue while leaving formal split
membership `not_added`. Discovery now prevents this Taiwan-wide-only context from creating future
review candidates; existing catalog records remain intact and readable.

Ongoing data curation must:

1. review each completed candidate against radar frames, synchronized evidence, and checksummed
   official context;
2. accumulate independently reviewed typhoon, frontal, Mei-yu, and convective regimes;
3. propose formal split changes separately and prevent overlapping candidate windows from crossing
   independent splits;
4. only after the dataset is meaningfully more diverse, rebuild it, retrain, and rerun the
   unchanged Persistence promotion gate.

Accumulating all target weather regimes is an ongoing observational requirement. The collector can
preserve and classify future evidence, but no regime should be claimed until a human review attaches
official weather context.
