# Offline event replay explorer

Issue #59 follows the immutable rolling backtest engine. Researchers need to inspect preserved
radar observations, forecasts, errors and source gaps without network access or manual labels.

## Delivery

Generate a self-contained local HTML using `mhc event replay`. A static export avoids a second
server, access controls and browser local-file fetch restrictions; compared with adding an API
route, it also gives researchers a portable snapshot. Embedded data contains whitelisted display
fields only. No source paths, acquisition URLs or credentials are exported. The export contains
research data and is private unless its owner chooses to share it.

Read the external checksum-enveloped backtest report, pinned manifest snapshot, forecast records,
arrays and score records. Reuse existing readers; do not regenerate forecasts or metrics. Verify
identity, source bytes/hashes, times and grids. Missing/corrupt artifacts produce explicit safe
states. Invalid top-level contracts fail with a fixed diagnostic. Resolve every input within the
configured external root, including symlinks. Refuse output collisions and outputs inside project
source or overwriting preserved inputs. Export can be placed in a new file below the external root
or a temporary directory. No changes to formal manifests or readiness gates.

Events have an observation-time slider and explicit previous/next/play/pause controls. Models and
leads are selected separately. Show target observation, stored forecast and signed error in three
aligned native-grid panels, plus common-mask saved metrics. If the selected observation has no
forecast, show its radar and an absent-forecast state. Acquisition time is unknown unless explicitly
provided; production time is separate. Native row/column coordinates, datum and downsampling are
visible; no geographic map, silent reprojection or interpolation. Preview by deterministic nearest
sampling (longest dimension <=160 by default); metrics remain full-resolution saved values.

Optional context manifest pins official QPE (O-B0045-001) and hourly gauge (O-A0002-001) artifacts
by event/time/path/bytes/hash, optional aware fetched_at and an explicit 60-minute interval.
Display QPE and gauges separately from instantaneous dBZ, each with its own datum and interval.
Only known hourly gauge fields are parsed. Mismatched times/intervals/unknown datums are explicit
invalid states; differing known datums stay segregated. No matching or new scoring in the UI.

Bound exports: at most 24 forecast origins and 120 observation frames by default, configurable
within hard limits; disclose omissions. No external assets, fonts, scripts, tiles or network calls.
A credential-free `--demo` builds synthetic native frames and real verified backtest artifacts in
a temporary directory, then uses the same exporter. Include empty/missing context states.

## Visual direction

Follow the existing operator interface: light slate background #f4f6f7, white work surfaces,
ink #202428, slate #4a6572, blue #2164a5 and amber #9b5c00 for absent data. Use system sans-serif
and tabular numerals, a compact tool header, labeled controls and a wide three-panel radar workbench.
The data panels carry the visual emphasis. Color legends, units and text states accompany color;
44px controls, visible focus, mobile stacking and no autoplay preserve accessibility. The design
search's hero/glass and neumorphic recommendations do not fit this research workflow; keep the
existing operator conventions and verified keyboard/control guidance.

## Verification

Real synthetic producer -> backtest -> export tests: verified arrays/saved metrics, source and
cache corruption, missing files, root escapes, no-valid pixels, config/event/time/grid drift,
script-safe JSON and no private paths; context units/interval/datum tests. Browser checks exercise
playback, keyboard slider, event/model/lead changes, empty states, mobile layout and zero network.
Bounded preserved official-data export demonstrates integration; raw data stays external.
