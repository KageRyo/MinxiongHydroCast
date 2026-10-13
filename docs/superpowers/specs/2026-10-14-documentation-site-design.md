# Documentation site design

## Intent and scope

Make the existing observation and research project understandable to visitors and usable by
contributors. The user approved the proposed documentation entry points, public documentation
site, and custom homepage, and authorized implementation, PR creation, and merge through GitHub
flow. Internal dashboard changes and live model/data promotion remain separate work.

## Architecture

MkDocs renders the existing `docs/` Markdown. Its bundled theme provides search, navigation,
and technical-page layout. A Jinja homepage override and local CSS provide a Traditional Chinese
project introduction. English technical documentation remains canonical. No Node application,
live API calls, credentials, analytics, external fonts, or official raw data are required.

The homepage introduces the Minxiong geographic boundary, official-source data flow, dated
independent-event model results, publication limitations, and four reading paths: quick start,
operations, data/research, and contribution. A geographic outline is derived from the committed
region profile and attributed as a reference boundary, not a flood-risk map.

## Visual direction

Use white `#ffffff`, mist `#eef5f7`, ink `#173443`, water `#086b83`, muted text `#47616d`,
and caution `#8a5200`. Use local system sans-serif/CJK fonts for text and tabular figures for
measurements. The primary composition pairs a left-aligned introduction with a Minxiong outline
and explicit source-to-validation diagram. Quiet spacing and restrained borders support reading.
Avoid decorative motion. Provide keyboard focus, reduced-motion support, mobile navigation,
responsive tables, and text explanations alongside semantic colors.

## Documentation and evidence

Add a credential-free quick start, API examples and HTTP/status interpretation, and a contributor
entry point. Keep dated operational evidence in deployment status and distinguish July evidence,
the September WRA freshness incident, and unverified current runtime status. Update README and
the documentation index to route readers rather than repeat changing runtime metrics.

## Build and delivery

Pin MkDocs in a docs-only requirements file. Strict builds must reject broken internal Markdown
links; generated-site validation checks actual local link and asset targets, including project
subpath URLs. PRs build the site; only main/manual main builds deploy to GitHub Pages with minimal
job permissions. Exclude theme sources and internal planning documents from published output.

## Acceptance

- Existing technical documents remain reachable through navigation or the complete index.
- Homepage, search, navigation, and reference links work at `/MinxiongHydroCast/`.
- Desktop and 375px mobile layouts are readable without page-level horizontal overflow.
- Site distinguishes demonstration, historical evidence, and current operational status.
- Strict site build, generated-link validation, existing lint/contracts/tests, and browser checks pass.
- Conventional Commits only; no Co-authored-by trailers. PR checks pass before authorized merge.
