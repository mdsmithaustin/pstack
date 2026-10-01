Here is the write-up. I went through the six rows and the incident log. My main worry is not any single row but how little of the evidence was gathered under Monday's conditions.

<file path="ops/premortem.md">
# Premortem: pre-push hook rollout

## Failure story

It is late October. The hook has been in for six weeks. Two engineers have stopped using worktrees because "the hook is weird in them", three people have posted `LEFTHOOK=0` pushes in the dev channel this week alone, and Priya has had to repair her checkout twice. Nobody can say what the hook is doing differently from CI, so the retry stays, the bypass gets used more, and the hook quietly stops being feedback.

## Row by row

**Row 1, flaky fixture test.** Two failures this year, both closed as flakes on the strength of a terminal rerun. That is a thin basis. Neither incident has a root cause written down, and both happened when the suite was started by git rather than by a person at a prompt. Keep the row, but its evidence is weaker than the register says.

**Row 2, slow pushes.** Solid numbers, a budget, and a fallback. Fine as written.

**Row 3, blocked hotfix.** `skip: hotfix/*` plus `LEFTHOOK=0` plus CI as the boundary already cover it. The approval step adds a page to an 11 minute path. Leave it out.

**Row 4, wrong branch after a failure.** The mitigation is "check which branch you are on afterwards". That is detection, not prevention. We do not know why Priya ended up on another branch, so we cannot say it will not happen again.

**Row 5, stray branches.** Cosmetic on its own. Suspicious together with row 4, since both come from the same two incidents.

**Row 6, suite writes into the team repo.** Likelihood 1 on the basis of 412 CI runs and a two week pilot. But CI runs the suite from a shell step in a fresh clone, and Dana's pilot was a plain clone. Seven of nine engineers use worktrees, and the suite has never been run from a hook in a worktree on purpose. The two times it happened by accident are INC-0514 and INC-0630, and both went badly. Whatever the cause, Likelihood 1 is not supported for the setup most of the team has.

## The check to run before Friday

Rows 4, 5, and 6 share a shape and we have never tried the actual Monday configuration. So try it, but not anywhere real.

1. Clone the repository to a throwaway directory, `/tmp/tally-trial`, and add a worktree from it, `git worktree add ../tally-trial.wt -b trial`.
2. Install the hook in the throwaway clone only (`lefthook install` from `/tmp/tally-trial`). Point `origin` at a second empty bare repo under `/tmp` so no push can reach the real remote.
3. Before pushing, write down `git rev-parse HEAD`, `git branch --list`, `git config core.bare`, and `git ls-files | wc -l` for the throwaway clone.
4. Make a one line commit in the worktree and push it, so the hook runs `make test-quick` exactly as it will on Monday.
5. Take the same four readings again.

Stop rule, decided before step 4 runs: any difference in the four readings, or a `zz-fixture-` branch appearing, or the worktree no longer on `trial`, means we do not adopt Monday. We then find out why before anything else happens. If all four match after three pushes, rows 4, 5, and 6 can keep their ratings and we adopt.

This costs one person about half an hour and touches nothing anyone works in. `rm -rf /tmp/tally-trial*` afterwards.

## Rollbacks

- Hook: `lefthook uninstall` per clone. Seconds. Already in the runbook.
- Checkout damage from a bad hook run: the runbook only says to look. Add the repair steps from INC-0514 (`git config core.bare false`, switch back, delete `zz-fixture-base`).

## Before Monday

1. Run the throwaway trial above and bring the readings to Friday.
2. Drop the row 3 approval step.
3. Add the repair steps to the runbook.
4. Reopen INC-0514 and INC-0630 with an actual root cause, even if the trial passes.
</file>

I have not changed any fixture code or the hook config. If the trial fails, that is when the fixture code needs looking at, and by then we will have a reproduction.
