# Incidents and oddities involving the test suite, 2026

Kept so the register has evidence instead of memory. Oldest first.

## INC-0409: hotfix during SEV-31

Priya pushed `hotfix/sev-31` from a fresh worktree at 14:02; CI green at 14:11; merged 14:13. No hook existed at the time. Nothing to fix. Recorded as the SEV path baseline.

## INC-0514: fixture failures from Priya's personal pre-commit hook

Priya had a personal `.git/hooks/pre-commit` that ran `make test-quick` (her own setup, never committed). Committing in worktree `tally-api.tkt-4821`, the fixture suite failed: 14 of 23 fixture tests, first error `fatal: this operation must be run in a work tree`, later ones `fatal: not a git repository`. Afterwards:

- `git branch --show-current` printed `zz-fixture-base`, not `tkt-4821`.
- A branch `zz-fixture-base` existed in the team repo with one commit, "fixture initial", on top of her tkt-4821 tip.
- `git status` refused to run until she set `git config core.bare false`.
- Her tkt-4821 work was intact once she switched back.

She captured the hook's environment while it was still broken:

```
$ env | grep '^GIT_'
GIT_AUTHOR_DATE=@1778769433 -0500
GIT_AUTHOR_EMAIL=priya@example.com
GIT_AUTHOR_NAME=Priya N
GIT_DIR=/Users/priya/src/tally-api/.git/worktrees/tally-api.tkt-4821
GIT_EDITOR=:
GIT_EXEC_PATH=/opt/homebrew/libexec/git-core
GIT_INDEX_FILE=/Users/priya/src/tally-api/.git/worktrees/tally-api.tkt-4821/index.lock
GIT_PREFIX=
```

`make test-quick` in a terminal from the same worktree passed 23 of 23. Closed: personal hook, not reproducible in a terminal or in CI, out of scope. She deleted the branch and removed the hook. Counted as flake 1 of 2 in the register.

## INC-0630: fixture failures under git rebase

Tomas ran `git rebase -x 'make test-quick' origin/main` in worktree `tally-api.tkt-5102` to test each commit. The fixture suite failed on the first commit with `fatal: this operation must be run in a work tree`. He had to run `git config core.bare false` before `git rebase --abort` would work, deleted a `zz-fixture-base` branch, then ran `make test-quick` in the terminal: 23 of 23. Closed as flaky; the proposal's retry comes from this. Flake 2 of 2.

## INC-0722: slow CI run

`make test-quick` took 3 m 41 s on a runner provisioned at the small size. Runner class fixed. Not test related.
