# Security Policy

## Supported versions

Security fixes are applied to the latest released minor version and the `main` branch.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Unreleased development branches | Best effort |

## Reporting a vulnerability

Do not open a public issue containing credentials, webhook URLs, private host details, unpublished
research data, or an exploitable vulnerability. Use GitHub's private vulnerability-reporting
channel for this repository when available, or contact the maintainer privately through the
contact method on the GitHub profile.

Include:

- affected version or commit;
- reproducible steps and expected impact;
- whether credentials, private data, or external systems may be involved;
- a minimal proof of concept with secrets and personal data removed.

The maintainer will acknowledge a complete report, assess severity, and coordinate a fix and
disclosure timeline. Do not test against official CWA/WRA systems beyond their documented
interfaces or attempt to access a deployment you do not own.

## Sensitive-data boundary

Safe to publish:

- source code, schemas, tests, synthetic samples, and API mocks;
- architecture, aggregate benchmarks, model cards, and license records;
- generic localhost/systemd templates with credentials and host paths omitted.

Keep private:

- API keys, cookies, Discord webhook URLs, and access tokens;
- CCTV, personal data, unpublished labels, raw research evidence, and model weights;
- live snapshots, logs, backup archives, hostnames, mount paths, runner identities, and internal
  deployment inventories;
- commercial delivery material or data without redistribution rights.

Local `.env` files, generated data directories, external research roots, checkpoints, documents,
archives, and Playwright artifacts are ignored by Git. Before every release, inspect staged files
and secret-scanning results; ignore rules do not make a committed secret safe.

## Service security posture

The supplied deployment binds services to loopback and is not a public-ingress design. Before
network exposure, add authenticated TLS ingress, least-privilege service ownership, remote backup,
rate limits, incident ownership, and completed observation/model gates. A healthy observation
snapshot does not authorize public forecast or emergency use.
