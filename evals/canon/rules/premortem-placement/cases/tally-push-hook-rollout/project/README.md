# tally-api

Billing Platform's invoice and account-config service. Python 3.12, pytest, Make.

## Tests

- `make test-quick`: lint, unit tests, and the fixture suite under `tests/fixtures/`. About 74 s on a CI runner, 60 to 90 s on a laptop.
- `make test`: everything above plus the contract tests against a live Postgres in Compose. CI runs this on every push to every branch.

CI is the enforcement boundary. Nothing merges without a green `make test` on the pull request.

## Working conventions

- One worktree per ticket: `git worktree add ../tally-api.tkt-NNNN -b tkt-NNNN` from the main checkout. Seven of the nine engineers on the team work this way; Dana and Marco keep a single plain clone and switch branches in it.
- Hotfixes go on `hotfix/*` branches and follow `ops/runbook-push-hook.md`.
- Changes to the shared developer workflow need a written proposal and a risk register signed off at the Friday team meeting. The current one is `ops/hook-proposal.md`.
