I read the proposal, the register, the runbook, the incident log, and the fixture README. The register treats six rows as independent. Four of them are one thing, and the evidence that rated it Likelihood 1 never exercised the path the team takes on Monday. The document below leads with that.

<file path="ops/premortem.md">
# Premortem: pre-push hook rollout

Written for the Friday decision. Assumes we adopted the hook on Monday 2026-09-14 and by the end of October it had cost us real work.

## The failure, stated first

Week one, a worktree user pushes. The hook runs `make test-quick`. Fourteen fixture tests fail with `fatal: this operation must be run in a work tree`. Afterwards the developer's checkout is on `zz-fixture-base`, a "fixture initial" commit sits on top of their ticket branch, `git status` refuses to run until they set `core.bare false`, and the retry has done all of it a second time. Multiply by seven engineers pushing several times a day. The damage is not the blocked push. It is the writes the suite made to the team repository from inside a hook, and the hour each person spends working out what happened to their checkout.

## The shared cause under rows 1, 4, 5, and 6

When git launches a program from a hook, or from `rebase -x`, it exports its repository variables into that program's environment. Priya captured exactly this in INC-0514: `GIT_DIR=/Users/priya/src/tally-api/.git/worktrees/tally-api.tkt-4821` and `GIT_INDEX_FILE=.../index.lock`. The fixture helper `run_git` passes `os.environ.copy()` through unchanged, by design, so that developer identity and signing settings apply inside the fixture. `cwd=` selects the repository only when `GIT_DIR` is unset. With `GIT_DIR` set, every call in `scratch_store()` acts on the team repository:

- `git init -b main <tmp>/work` reinitialises the existing repo, which is why `core.bare` ends up flipped.
- `git checkout -b zz-fixture-base` creates that branch in the team repo and moves the developer's HEAD onto it. That is row 5, and the branch confusion in row 4.
- `git commit -m "fixture initial"` lands on top of the developer's ticket tip. That is the stray commit INC-0514 describes.
- The `fatal: this operation must be run in a work tree` messages are the calls that came after the bare flip. That is the "flake" in row 1.

So rows 1, 4, 5, and 6 are one risk with one cause, and row 6's Likelihood 1 is wrong. Reread the evidence with that in mind:

- 412 green CI runs: CI runs `make test-quick` as a plain shell step in a fresh clone. No hook, no `GIT_DIR`. Zero in-git launches.
- Daily terminal runs: same, zero in-git launches.
- Dana's pilot, 31 pushes: from a plain clone, where the hook's `GIT_DIR` is most likely the relative `.git`, which from the fixture's `cwd` resolves inside the scratch directory. That is the likeliest reason the pilot was clean, and it means the pilot tested the two engineers who do not use worktrees.
- INC-0514 and INC-0630: the only two times the suite has ever run from inside git in a worktree, and both did exactly this.

Two of two in-git worktree launches failed. Seven of nine engineers work from worktrees. From Monday, the hook is an in-git worktree launch on every push.

The retry makes it worse, not better. `|| make test-quick` runs in the same environment, so it repeats the writes.

## The one check to run before Friday

Assumption under test: `GIT_DIR` from a hook in a worktree reaches the fixture git calls and they act on the outer repository.

Run it only on a scratch clone. Nobody's working checkout, nobody's remote.

1. `git clone <team repo> /tmp/tally-scratch && cd /tmp/tally-scratch`, then `git worktree add ../tally-scratch.wt -b scratch-wt`.
2. Record the baseline in the scratch clone: `git rev-parse HEAD`, `git branch --list`, `git config core.bare`, `git ls-files | wc -l`.
3. In the worktree, run the suite the way the hook will: `GIT_DIR=$(git rev-parse --absolute-git-dir) make test-quick`. This is the same variable Priya's capture shows, without installing any hook.
4. Record the same four values again.

Stop rule, fixed now, before anyone runs step 3: if any of the four values differs, or the worktree's current branch is no longer `scratch-wt`, we do not adopt on Monday. The fix is to strip `GIT_*` in `run_git` (keep `GIT_AUTHOR_*` and `GIT_COMMITTER_*` if identity matters, drop the rest) or to have the hook command unset `GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE` before `make`. Then rerun steps 1 to 4 on a fresh scratch clone and adopt only when nothing moves.

If all four values match, the cause analysis above is wrong about this git version and the register stands. Either way we know before Friday, and no real checkout was touched to find out.

## Rollbacks

- Trigger: `lefthook uninstall` from the main checkout, or delete `.git/hooks/pre-push`. Seconds, per clone. Already in the runbook.
- Damage already done to a checkout: `git config core.bare false`, `git switch <ticket branch>`, `git branch -D zz-fixture-base`, then `git log -1` to confirm the "fixture initial" commit is not on the ticket branch. If it is, `git reset --hard HEAD~1` after checking `git show --stat HEAD` is the fixture commit. This belongs in the runbook before Monday, because uninstalling the hook does not undo it.

## What is fine as written

- Row 2, push latency. p50 74 s, p95 118 s, and the 120 s budget with a stated fallback (drop lint). Leave it.
- Row 3, hotfixes during a SEV. `skip: hotfix/*` keeps the hook off the SEV path, `LEFTHOOK=0` covers a misnamed branch, CI stays the boundary. The bypass approval step adds a page and a chat confirmation to an 11 minute path and protects against nothing the skip does not already cover. Drop it rather than add it.
- CI unchanged, branch protection unchanged. Correct, and the reason the blast radius here is checkouts and not main.

## Change before Monday

1. Run the scratch check above before Friday and bring the four before/after values to the meeting.
2. Fix `run_git` to strip `GIT_*` (or unset them in the hook command), with a test that runs the suite under an absolute `GIT_DIR` pointing at a scratch clone and asserts HEAD, branch list, `core.bare`, and tracked-file count are unchanged. The proposal says leave fixture code alone for now; this is the one exception the evidence forces.
3. Remove `|| make test-quick`. The two "flakes" it was added for were this cause, not flakiness.
4. Collapse register rows 1, 4, 5, and 6 into one row with the real cause, Likelihood 5 until the fix lands, Impact 4.
5. Drop the row 3 approval step.
6. Add the damage rollback above to the runbook.
7. Reopen INC-0514 and INC-0630 as one root-caused incident, not two flakes.
</file>

I left the fixture code and `lefthook.yml` as they are, per your note. The document names the change to `run_git` as a Monday blocker but does not make it.
