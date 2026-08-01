# Contributing to MinxiongHydroCast

Thank you for helping improve the project. Minxiong is the reference implementation; reusable
contracts, synthetic fixtures, documentation, and fail-closed source handling are especially
welcome.

## Find or propose work

Use GitHub Issues for public, collaboration-safe work. A good issue states the observable problem,
the expected contract, and evidence that would prove completion. Maintainers may keep private
operational review, credentials, unpublished event evidence, host details, or restricted source
material outside GitHub.

Good starting areas include:

- documentation and synthetic examples;
- region-profile validation;
- adapter contract tests using fixture transports;
- package and Docker demo portability;
- research baselines that retain Persistence as the benchmark.

Do not post API keys, private event identifiers or notes, raw official captures with unclear
redistribution rights, production paths, notification recipients, or deployment secrets.

## Development setup

Python 3.11 and 3.13 are supported.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Install only the capability extras needed by your change:

```bash
python -m pip install -e ".[scraper]"
python -m pip install -e ".[model]"
python -m pip install -e ".[report]"
```

Before opening a pull request, run:

```bash
python -m compileall -q src tests scripts
python -m ruff check .
python -m pytest -q
python -m build
```

For packaging or demo changes, also verify a wheel in a clean virtual environment and run:

```bash
mhc --help
mhc collect --region minxiong --mode demo --once
```

## Region profiles

Tracked profiles live in `src/minxionghydrocast/profiles/` and use JSON-compatible YAML so the
base package does not need a YAML dependency. Start with `example-region.yaml`, replace its
placeholder boundary, use exact authority codes/names, and add tests for filtering, freshness,
coverage, and package inclusion. A new profile does not imply that its live sources or forecast
capability are operationally supported.

## Data-source adapters

Follow [the adapter development guide](docs/adapter_development.md). Tests must use deterministic
fixture transports by default. Live contract probes belong in explicitly scheduled workflows and
must read credentials from protected environment variables.

## Pull requests

Keep changes focused, preserve source provenance and fail-closed behavior, and explain:

- what user-visible contract changed;
- which synthetic or rights-reviewed evidence verifies it;
- whether schemas, source behavior, dependencies, or deployment are affected;
- which publication, notification, data, or model gates remain blocked.

## Releases

Publishing is intentionally separated from ordinary CI. A maintainer creates a GitHub release only
after the version, changelog, package build, and synthetic smoke test agree. The release workflow
builds the distributions again and publishes through PyPI Trusted Publishing; it does not use a
repository API-token secret.

Before the first publication, a project owner must configure the PyPI project to trust
`.github/workflows/release.yml` in this repository with the `pypi` GitHub environment. Protect that
environment with required reviewers where the repository plan supports it.

By contributing, you agree that your code contribution is licensed under the repository's MIT
License. That does not grant redistribution rights for third-party data or documents.
