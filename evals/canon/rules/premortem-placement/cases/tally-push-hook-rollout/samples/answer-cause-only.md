Short version: the register's two "flakes" are not flakes, and the row that carries the only Impact 5 outside the SEV path is rated on evidence that never took the path we are adopting.

<file path="ops/premortem.md">
# Premortem: pre-push hook

## What hurt us

The fixture suite wrote into developers' checkouts from inside the hook. Branch flipped to `zz-fixture-base`, a stray "fixture initial" commit on the ticket branch, `core.bare` set to true. INC-0514 and INC-0630 describe it exactly, once from a personal pre-commit hook and once from `rebase -x`. Both were closed as flakes because a terminal rerun passed. A terminal rerun passes because the terminal is not git.

## Why

Git exports `GIT_DIR` and `GIT_INDEX_FILE` to hooks. Priya's environment capture in INC-0514 shows `GIT_DIR` pointing at her worktree's gitdir under the team repo. `run_git` in `tests/fixtures/conftest.py` passes `os.environ.copy()` straight through, and `GIT_DIR` overrides `cwd`, so `git init`, `git checkout -b zz-fixture-base`, `git commit`, and `git push` in `scratch_store()` all act on the team repository. Rows 1, 4, 5, and 6 of the register are this one mechanism seen from four angles.

Row 6's Likelihood 1 rests on 412 CI runs (plain shell, no hook) and Dana's pilot (a plain clone, not a worktree). Neither is an in-git launch from a worktree. The only two of those we have both failed. Seven of nine engineers push from worktrees.

The `|| make test-quick` retry runs in the same environment and repeats the writes.

## What is fine

- Row 2 (latency) is well evidenced and has a fallback. Keep it.
- Row 3 (SEV hotfix) is covered by `skip: hotfix/*`, `LEFTHOOK=0`, and CI as the boundary. The approval step is extra process for no extra safety. Do not add it.

## Change before Monday

1. Fix `run_git` to drop `GIT_*` from the environment it passes (or unset `GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE` in the hook command). This is a blocker for Monday, not a follow-up.
2. Remove the retry.
3. Merge rows 1, 4, 5, and 6 into one row with the real cause.
4. Add a recovery section to the runbook: `git config core.bare false`, switch back to the ticket branch, delete `zz-fixture-base`, check the ticket tip for the stray commit.
5. Reopen INC-0514 and INC-0630 as one root-caused incident.

Once the `run_git` change has landed and CI is green on it, the suite is safe to run from a hook and the register can go back to the Friday shape minus the approval step.
</file>

I did not touch `conftest.py` or `lefthook.yml`. Item 1 is the change I would make first thing Thursday.
