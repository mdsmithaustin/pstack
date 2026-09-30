# Runbook: the pre-push hook

## Install

Once per clone, from the main checkout: `brew install lefthook && lefthook install`. Worktrees share the clone's hooks.

## When the hook fails

1. Read the failure. If it is your change, fix it and push again.
2. If `make test-quick` passes when you run it in a terminal, treat it as a flake. The hook already retried once. Push with `LEFTHOOK=0 git push` and post the test name in #billing-platform-dev.
3. After any hook failure run `git status` and `git branch --show-current` before doing anything else. See INC-0514 in ops/incidents.md for why.

## Hotfixes during a SEV

1. Branch from main: `git worktree add ../tally-api.hotfix -b hotfix/<sev-id>` (or `git switch -c hotfix/<sev-id>` in a plain clone).
2. Push. The hook does not run on `hotfix/*`. If it somehow does and fails, `LEFTHOOK=0 git push`.
3. Open the PR with the SEV id in the title. CI runs `make test`; the on-call merges on green. Branch protection still applies; there is no path that skips CI.

INC-0409 is the reference: hotfix branch to merged in 11 minutes, of which CI was 9.

## Uninstall

`lefthook uninstall` from the main checkout, or delete `.git/hooks/pre-push`. Takes seconds and affects only your clone.
