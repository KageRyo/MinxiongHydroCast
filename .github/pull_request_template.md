## Outcome

Describe the user-visible result and the contract it changes.

## Verification

- [ ] `python -m compileall -q src tests scripts`
- [ ] `python -m ruff check .`
- [ ] `python -m pytest -q`
- [ ] Package/demo smoke test if packaging, CLI, or runtime startup changed

List focused tests and artifact evidence:

## Source, data, and safety review

- [ ] No credentials, host-specific details, private event review, or restricted raw data are included.
- [ ] Schema drift and invalid/empty/stale inputs still fail closed where required.
- [ ] Forecast publication, notification, and formal-split gates were not weakened.
- [ ] New dependency, source, redistribution, or deployment implications are documented.

## Remaining limits

State what this change intentionally does not claim or enable.
