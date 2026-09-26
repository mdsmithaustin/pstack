## What does this PR do?

`/topup → Monthly limit` has been read-only since Phase 2b: it prints `$180 of $1000 used this month` and points admins at the portal. Portal now accepts `PUT /api/billing/monthly-cap` from `billing:manage` tokens and returns the org's `ceilingUsd` in `monthlyCap` on `/api/billing/state`, so an admin can change the limit without leaving the terminal.

For an admin with Remote Spending on, the Monthly limit screen now offers **Change limit**, prompts for the new amount (showing the ceiling), checks it locally for instant feedback, and sends the PUT. Non-admins and orgs with the kill-switch off get the same gate copy as Add funds and Auto-reload. Setting a limit below what's already spent this month is allowed (the server accepts it); the screen just says new charges will be refused until the month resets.

The auto-reload PATCH wrapper becomes `_billing_mutate(state, call, **kwargs)` so both settings go through the same scope step-up and error rendering.

## Related Issue

Follow-up to the Remote Spending work; the TUI overlay (`ui-tui/src/components/billingOverlay.tsx`) still shows the limit read-only and will get the same action in a separate PR.

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [x] ✨ New feature (non-breaking change that adds functionality)
- [ ] 🔒 Security fix
- [ ] 📝 Documentation update
- [ ] ✅ Tests (adding or improving test coverage)
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🎯 New skill (bundled or hub)

## Changes Made

- `agent/billing_view.py`: `MonthlyCap.ceiling_usd` parsed from `monthlyCap.ceilingUsd`; new `validate_monthly_limit(raw, *, ceiling_usd)`.
- `hermes_cli/nous_billing.py`: `put_monthly_cap(limit_usd=...)`.
- `hermes_cli/cli_billing_mixin.py`: Monthly limit screen gains the change flow; `_billing_patch_auto_top_up` → `_billing_mutate`; menu copy updated.
- Tests: limit validation and ceiling parsing (`tests/agent/test_billing_view.py`), the PUT body (`tests/hermes_cli/test_nous_billing_request.py`), and the screen end to end with scripted input (`tests/hermes_cli/test_cli_billing_limit.py`).

## How to Test

1. `scripts/run_tests.sh tests/agent/test_billing_view.py tests/hermes_cli/test_nous_billing_request.py tests/hermes_cli/test_cli_billing_limit.py`
2. Against a staging portal as an org owner: `/topup → Monthly limit → Change limit`, enter an amount above the ceiling (refused locally, no request sent), then a valid one.
3. Confirm the portal billing page shows the new limit, and `/topup → Monthly limit` shows it on the next open.

## Checklist

### Code

- [x] I've read the [Contributing Guide](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md)
- [x] My commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`fix(scope):`, `feat(scope):`, etc.)
- [x] I searched for [existing PRs](https://github.com/NousResearch/hermes-agent/pulls) to make sure this isn't a duplicate
- [x] My PR contains **only** changes related to this fix/feature (no unrelated commits)
- [x] I've run `pytest tests/ -q` and all tests pass
- [x] I've added tests for my changes (required for bug fixes, strongly encouraged for features)
- [x] I've tested on my platform: Ubuntu 24.04

### Documentation & Housekeeping

- [ ] I've updated relevant documentation (README, `docs/`, docstrings) — or N/A
- [x] I've updated `cli-config.yaml.example` if I added/changed config keys — or N/A
- [x] I've updated `CONTRIBUTING.md` or `AGENTS.md` if I changed architecture or workflows — or N/A
- [x] I've considered cross-platform impact (Windows, macOS) per the [compatibility guide](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md#cross-platform-compatibility) — or N/A
