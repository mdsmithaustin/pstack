Done. The interesting finding is in the incident log rather than the register: the two "flakes" have the same fingerprint, and the register does not connect them to the row it should.

<file path="ops/premortem.md">
# Premortem: pre-push hook rollout

## Headline

By mid October, worktree users have had their checkouts rewritten by the fixture suite running inside the hook, and the team has turned the hook off for everyone but Dana and Marco.

## The mechanism

Both INC-0514 and INC-0630 are the suite being started by git rather than by a shell. In that situation git exports `GIT_DIR` (Priya's capture shows it pointing at `.git/worktrees/tally-api.tkt-4821`) and `GIT_INDEX_FILE`. `run_git` copies the whole environment into every fixture call, and `GIT_DIR` wins over `cwd`. So `scratch_store()` does its `git init`, `git checkout -b zz-fixture-base`, `git commit -m "fixture initial"`, and `git push` against the team repository, not the temp directory. That gives you all four symptoms at once: the bare flag, the branch switch, the stray commit, and the `not a work tree` errors that the register calls a flake.

Rows 1, 4, 5, and 6 are therefore one row. Row 6's Likelihood 1 comes from CI (a shell step, no `GIT_DIR`) and from Dana's pilot (a plain clone). It has never been rated on a hook in a worktree, which is what seven of nine of us will run on Monday. The retry doubles the writes.

## Confirming it

The cheapest confirmation is to run it for real, once, with someone watching. Monday morning before standup, Priya installs the hook in her main checkout, makes a one line commit in her current ticket worktree, and pushes it while Tomas watches `git status` and `git branch --show-current` in that worktree. If the branch flips or `core.bare` changes, we uninstall immediately, Priya repairs her checkout as she did in INC-0514, and the fix to `run_git` goes in before anyone else installs. If it is clean, the rest of the team installs after standup as planned. Half an hour, one person's checkout, and we know for certain instead of arguing about it on Friday.

## Fine as written

- Row 2. Good numbers, clear fallback.
- Row 3. Skipped by branch pattern, bypass available, CI unchanged. The approval step adds nothing. Drop it.

## Change before Monday

1. Strip `GIT_*` from the environment in `run_git`, or unset `GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE` in the hook command before `make`. Ideally this lands before the Monday check above so the check confirms the fix rather than the bug, but if it cannot, the check still tells us where we stand.
2. Remove `|| make test-quick`.
3. Collapse rows 1, 4, 5, 6 into one row named for the cause.
4. Add checkout repair steps to the runbook.
5. Drop the row 3 approval step.
</file>

Fixture code and hook config left as they were. The `run_git` change is a five line diff when you want it.
