# Proposal: run test-quick from a pre-push hook

Author: Tomas. Decision: Friday 2026-09-11 team meeting. Rollout: the following Monday; everyone runs `lefthook install` once per clone.

## Why

Since May, 9 of 61 pull requests went red on their first CI run for something `make test-quick` would have caught on the laptop (lint, a unit test, a fixture test). Each cost a CI cycle of about 12 minutes plus a context switch. A pre-push hook moves that feedback to the laptop.

## Change

Add `lefthook.yml` at the repo root and commit it:

```yaml
pre-push:
  commands:
    test:
      skip:
        - ref: hotfix/*
      run: make test-quick || make test-quick
```

The `|| make test-quick` retries once, because both local failures reported this year passed on rerun (ops/incidents.md). `skip` on `hotfix/*` keeps the hook out of the SEV path. `LEFTHOOK=0 git push` bypasses the hook for anything else; the runbook says when that is acceptable.

Hooks are installed into the main checkout's `.git/hooks`, so one `lefthook install` covers every worktree of that clone. Worktree users do nothing per ticket.

## Timing

`make test-quick` over the last 412 CI runs: p50 74 s, p95 118 s, max 3 m 41 s (one undersized runner, INC-0722). Budget is 120 s per push. If p95 crosses it we drop lint from the hook and keep it in CI.

## Pilot

Dana ran the hook on her laptop for two weeks (2026-08-17 to 2026-08-28): 31 pushes, 2 hook failures, both real (a unit test she had broken), median 66 s. No other effects. Dana works from a plain clone.

## Not changing

- CI still runs the full `make test` on every push. The hook is feedback, not enforcement.
- The fixture suite is unchanged. It has been green for 412 consecutive CI runs.
- Branch protection is unchanged.

## Open question for Friday

The register proposes a bypass approval step for hotfixes (row 3). Marco wants it; Priya thinks `skip` plus `LEFTHOOK=0` already cover it. Decide Friday.
