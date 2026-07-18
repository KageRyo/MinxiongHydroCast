# Deployment status

This page records verified deployment evidence. It does not claim that MinxiongHydroCast is an
official warning system or authorize external operational use.

## Verified on 2026-07-13

The single-host shadow deployment is running on Linux host `RTX4090` with user-systemd linger
enabled. Mutable state is stored under `/mnt/8tb_hdd/ryo/minxiong-hydrocast`, and the stable
service path is `~/.local/share/minxiong-hydrocast`. Its private environment file has mode `0600`
and is not tracked by Git.

Verified runtime components:

- collector timer every ten minutes, with strict CWA/WRA API sources;
- localhost API and operator view on `127.0.0.1:8180`;
- Prometheus 3.13.1 on `127.0.0.1:9090`, scraping the API target successfully;
- Alertmanager 0.33.1 on `127.0.0.1:9093`;
- Pydantic-validated alert audit receiver on `127.0.0.1:9087`;
- daily backup and hourly shadow-evaluation timers;
- concise `mhc` command dispatcher available through the stable user path;
- dedicated runner `RTX4090-minxiong-hydrocast`, online with the `minxiong-hydrocast` label, for
  source contracts that require host credentials.

The post-migration live snapshot was healthy and ready. It contained a valid empty WRA
rainfall-warning product, 82 CWA rain-gauge observations, 150 WRA IoW flood-sensor observations,
and a ready Minxiong feature row.

## Continuous event evidence rollout verified on 2026-07-14

PR #12 deployed the continuous event-evidence workflow from merge revision
`7f8fccc8f93a5261dab6be47550b9b11d5f9b25a`. The recorded installed revision matched `main`, the
private systemd environment remained mode `0600`, and
`MINXIONGHYDROCAST_RESEARCH_ROOT` resolved to the external durable research volume.

The `minxiong-hydrocast-event-discover.timer` was enabled and active on a 20-minute schedule. Its
first installed oneshot completed successfully after scanning 33 new frames and triggers. The
12:00 run summary was also `status=ok`, reported no evidence errors, and incrementally scanned two
new trigger frames without changing any formal dataset split.

At the 2026-07-14 12:00 evidence snapshot, the strict catalog contained one active candidate:

- 82 of 88 required 10-minute radar frames were captured;
- 76 trigger frames extended the candidate through 11:50, with a provisional window end at 12:50;
- 18 synchronized evidence captures each reported QPE/gauge/warning states `ok/ok/empty`;
- full catalog artifact verification reported zero checksum or size errors;
- review state remained `collecting`, `pending`, `unclassified`, and `not_added`.

These counts are a dated operational snapshot. The candidate later completed and received the
review recorded below. The formal five-event split remained unchanged with SHA-256
`953b8b0d85b0269adcc7468288332e039d01512a0ac626090efbf56b12a6a6e1`.

## Bounded candidate rollout and first review verified on 2026-07-14

Revision `607ceee994fe15f77ee6a82eb1382f60f9df4b04` deployed a 480-minute maximum total
candidate window. The installed revision matched `main`; the installed CLI, systemd unit, and run
summary all recorded the new bound. The rollout preserved the existing candidate's identifier,
trigger set, and window end, while a qualifying 16:40 frame started a second candidate. The first
post-deploy run reported two candidates, no evidence errors, and zero catalog artifact verification
errors. The localhost API remained healthy and ready, and Prometheus and Alertmanager remained
ready.

Candidate `cwa_o_a0059_candidate_20260713t2320` then completed its fixed 22:20-17:30
window with 116 of 116 radar frames, 104 qualifying triggers, and 32 synchronized
QPE/gauge/warning captures, all `ok/ok/empty`. Only the 12:20 frame met the Minxiong-local trigger:
37.8 dBZ across three local pixels. The configured Minxiong QPE point peaked at 0.5 mm, the four
latest Minxiong gauges each reported 0 mm over one hour, and WRA returned no active rainfall
warning.

The review recorded `approved`, `convective`, and reviewer `KageRyo (Codex-assisted)` at 17:42.
It preserved the CWA W01 report issued at 11:00 as a 74,278-byte external artifact with SHA-256
`7010c4e498a95b99a2746f20a89fe6f4f49b78e7c5b20351dc18ef22b27f9d90`. The report's
southern-cloud-system and localized shower/thunderstorm description supported the classification;
the review explicitly did not treat the candidate as flood or warning evidence. Full verification
reported zero errors after the review, and an identical review command returned
`catalog_changed=false`. Formal membership remained `not_added`, and the formal manifest retained
the same SHA-256 recorded above.

## Follow-up candidate reviews verified on 2026-07-15

The 09:00 discovery cycle reported four candidates, three complete windows, and zero evidence
errors. Full Pydantic and artifact checksum verification also reported zero errors. Two complete
windows were Taiwan-wide context rather than Minxiong-local events:

- `cwa_o_a0059_candidate_20260714t1640` contained 18 of 18 frames, six Taiwan-wide triggers, zero
  Minxiong-local triggers, and four synchronized `ok/ok/empty` captures. Its local radar peak was
  8.0 dBZ.
- `cwa_o_a0059_candidate_20260715t0020` contained 18 of 18 frames, six Taiwan-wide triggers, zero
  Minxiong-local triggers, and three synchronized `ok/ok/empty` captures. It had no valid local
  reflectivity peak.

Both reviews recorded `rejected/unclassified` for the Minxiong-local queue and explicitly did not
classify the broader Taiwan weather state. Their formal membership remained `not_added`; the
formal manifest SHA-256 remained
`953b8b0d85b0269adcc7468288332e039d01512a0ac626090efbf56b12a6a6e1`.

At the same dated snapshot, the fourth pre-policy candidate remained collecting with 28 of 34
frames, 21 Taiwan-wide triggers, and zero Minxiong-local triggers. It remains preserved as existing
evidence and can finish its already-defined window; it does not justify creating more local review
work.

The candidate policy retains Taiwan-wide labels and coverage in persisted frame metrics but allows
only `minxiong_35dbz` frames to create or extend future review candidates. Compatibility tests
and a direct read of the live catalog confirm that the older config parses with this default, all
four candidate records remain readable, and artifact verification still reports zero errors. No
destructive catalog migration is required.

## Runtime and review queue verified on 2026-07-18

The repository, `origin/main`, and installed single-host revision all matched
`536a7a5e087b3e793011d318fb7d2f63d3bd4b43`. There were no open pull requests. CI for the merge and
the scheduled Official Live Contracts runs from July 15 through July 18 passed. The API,
Prometheus, Alertmanager, and alert audit receiver were active; collector, event-discovery, shadow,
and backup timers were scheduled and their latest oneshot results succeeded.

The 14:20 live observation run was healthy and ready. It preserved a valid empty rainfall-warning
product, 81 CWA rain-gauge observations, 150 WRA flood-sensor observations, 231 location-reference
rows, and one ready Minxiong feature row. The July 18 daily backup contained 748 snapshots and
passed archive SHA-256 verification with digest
`3438ee41b5aa5fd8d2703691e633789c3b43c7d650fd067cf20d3495e338a06e`.

The 14:20 event-discovery run used `candidate_trigger_label=minxiong_35dbz`, scanned two local
trigger frames, and left the strict catalog at nine candidates with zero artifact errors. Eight
candidates were complete. The five complete pending reviews were:

- the preserved pre-policy context-only candidate
  `cwa_o_a0059_candidate_20260715t0520`, with 35 of 35 frames, 22 Taiwan-wide triggers, zero local
  triggers, and a 31.5 dBZ local peak;
- `cwa_o_a0059_candidate_20260715t1840`, with 16 of 16 frames, three local triggers, and a
  42.8 dBZ local peak;
- `cwa_o_a0059_candidate_20260716t1730`, with 20 of 20 frames, eight local triggers, and a
  55.5 dBZ local peak;
- `cwa_o_a0059_candidate_20260717t1330`, with 47 of 47 frames, 29 local triggers, and a
  55.0 dBZ local peak;
- `cwa_o_a0059_candidate_20260718t1140`, with 18 of 18 frames, six local triggers, and a
  47.5 dBZ local peak.

Candidate `cwa_o_a0059_candidate_20260718t1400` remained collecting with 8 of 14 frames and two
local triggers at the verification point. All new local candidates had synchronized evidence with
valid QPE and gauge artifacts and empty WRA warning products. These reflectivity thresholds are
review candidates, not proof of heavy rain, flooding, or an official warning. Formal split
membership remained `not_added` for every discovery candidate.

## Operational drills

The original `MinxiongHydroCastDrill` and post-migration `MinxiongHydroCastMigrationDrill`
synthetic alerts produced durable local notification audit records. This proves local
Prometheus/Alertmanager routing and receiver persistence; it does not provide a named human
notification channel. An allowlisted, bounded, retrying Discord incoming-webhook backend is
implemented, but the deployed notification environment is deliberately empty pending explicit
activation and assignment of a named owner.

The post-migration backup drill created and SHA-256 verified a 68-snapshot archive. It restored the
archive into an isolated durable drill directory, verified every snapshot, and confirmed that the
restored latest snapshot ID matched the archive metadata.

The manually dispatched Official Live Contracts run `29219192303` passed both jobs:
GitHub-hosted CWA/IoW contracts and the host-bound WRA rainfall-warning contract on the renamed
self-hosted runner.

The original deployment suite passed with 237 tests. The continuous event-evidence rollout later
passed 268 tests in PR CI, and Ruff reported no issues.

## Canonical identifier rollout

The canonical identifier rollout is complete. The GitHub repository and local remote, durable
root, stable service link, private environment paths, Python distribution and entry points,
Prometheus rules and live metric prefix, user-systemd units and timers, and self-hosted runner all
use the identifiers defined in [project_identity.md](project_identity.md).

The runtime migration used a same-filesystem directory rename rather than copying state. Before
the move, all 66 retained snapshots passed application-level integrity verification and a fresh
backup was verified. After the move, checksums for all 396 pre-existing immutable snapshot files
matched, and the store continued to 68 healthy attempts without resetting its first observation.
The shadow report retained a 100% success and readiness rate, a 10.283-minute maximum gap, and a
passing storage-integrity check. Historical Prometheus samples remain in the existing TSDB while
the live endpoint exports only the `minxionghydrocast_` prefix.

All canonical services and timers are enabled, old unit files and timer stamps are absent, the API
and operator view return HTTP 200, Prometheus reports its API target up, Alertmanager is ready, and
the runner is listening under its canonical name and label. Discord delivery was not activated by
the migration.

## Active shadow gate

The shadow deployment started on 2026-07-12. A read-only evaluation at 2026-07-18 14:29 retained
819 live attempts over 134.760 hours. Of those attempts, 803 succeeded and 792 were ready, for
98.0464% success and 96.7033% readiness. Storage integrity and evidence-file validation passed,
but the maximum ready-data gap was 50.017 minutes and there was no reviewed heavy-rain period.

The 16 failed attempts were WRA responses that returned invalid JSON or transiently failed strict
response validation. Eleven additional successful snapshots were not ready because official CWA
rain gauges or WRA flood sensors were stale. The current feeds had recovered and the latest
snapshot was healthy. This evidence requires a bounded transient-response reliability change; it
does not justify weakening Pydantic contracts or treating a repeatable schema change as healthy.

The gate remains blocked by design until all of the following are observed rather than simulated:

- at least 168 hours between the first and last retained live attempt;
- at least 900 attempts in the eight-day audit window;
- at least 99% collection success and 95% readiness;
- no ready-data gap over 30 minutes and no storage-integrity error;
- continuous ready coverage during at least one reviewed, confirmed heavy-rain period.

External operational use and automated risk notification must remain disabled while those
conditions are incomplete. A qualifying heavy-rain period may require the shadow deployment to
run longer than seven calendar days. Even if no new gap occurs, the latest recorded gap over 30
minutes remains inside the 192-hour audit window until approximately 2026-07-25 23:21
Asia/Taipei. Internal code, documentation, evidence review, and reliability changes may merge
independently when their own review and CI checks pass.

## Outstanding safeguards

- Continue collecting reviewed typhoon, frontal, Mei-yu, and convective regimes. Retraining and
  formal split expansion remain blocked until the dataset is meaningfully more diverse.
- Explicitly activate the implemented Discord backend only after naming its primary and backup
  on-call owners, then exercise its incident path.
- Before any external operational use, replicate backups to another device or remote system. The
  current backup protects snapshots from application-level corruption but not loss of the whole
  host or volume.
- Assign incident ownership and exercise acknowledgement, override, and rollback responsibilities.
- Complete the real shadow gate and local model/label gates before enabling risk notifications.
- Add authenticated TLS ingress only if the localhost service must become network-accessible.
