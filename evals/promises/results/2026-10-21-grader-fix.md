# Grader fix reruns, 2026-10-21

**Status: COMPLETE.** [2026-10-20-sync-7a9a3ddb.md](./2026-10-20-sync-7a9a3ddb.md) left 7 runs refused at grading and two Claude Code FAILs measured once. This wave reruns those cases with the grader from this branch and the skills at `8731b6eb`. Every run graded. No run was refused and no batch stopped.

No `--model` or `--effort` was passed, so each harness ran its configured default at high effort. The run directories are kept outside the repository, under `pstack-live-runs/2026-10-21-grader-fix/`.

## Previously refused runs

| harness | case | refusal on 2026-10-20 | now | what the run exercised |
|---|---|---|---|---|
| grok | `route-code-review` | `unapproved_worktree` | PASS | A review worktree registered under `<run>/tmp` was graded. |
| grok | `feature-run` | `unapproved_worktree` | graded, no FAIL | No worktree under `<run>/tmp` this time. |
| grok | `feature-run-no-todo` | `unapproved_worktree` | 1 PASS, 1 FAIL (ORACLE, below) | No worktree under `<run>/tmp` this time. |
| grok | `route-babysit` | `unsafe_link` | PASS | The lead launched watch-pr. No `node_modules` remained at grading. |
| grok | `route-babysit-check` | `unsafe_link` | PASS | The lead launched watch-pr. No `node_modules` remained at grading. |
| hermes | `route-refactoring` | `unapproved_worktree` | PASS | No worktree this time. |
| hermes | `route-autonomous-run` | `unapproved_worktree` | INCONCLUSIVE | Three arena worktrees registered under `<run>/tmp` were graded. |

The run that registered worktrees in the Hermes profile cache is covered by `test_live.ScratchWorktrees`, not by this wave.

## Claude Code repeats

`sticky-followup` and `feature-run` ran 3 times each.

| promise | case | verdicts |
|---|---|---|
| `worklist-opens-with-playbook-steps` | `feature-run` | PASS 3 |
| `worklist-in-native-task-tool` | `feature-run` | PASS 3 |
| `poteto-mode-reads-principles-and-names-applied` | `feature-run` | FAIL 1, INCONCLUSIVE 2 |
| `reply-says-inconclusive-when-check-cannot-run` | `feature-run` | FAIL 1, INCONCLUSIVE 2 |
| `poteto-mode-sticky` | `sticky-followup` | FAIL 1, PASS 2 |
| `short-prompt-continues-in-context` | `sticky-followup` | FAIL 1, PASS 2 |
| `new-task-rematches` | `sticky-followup` | FAIL 2, PASS 1 |
| `read-only-phrase-pins-investigation` | `sticky-followup` | PASS 3 (2 are wrong, below) |

The worklist promise failed on Claude Code in both earlier waves and passed 3 of 3 here. The skills tree changed between them, so this wave does not show which change fixed it. The bisect of `e7f0abe3` that the baseline proposed is no longer needed.

## FAIL classes

Each FAIL's trace was read before it was tallied.

| promise | harness | run | class | finding |
|---|---|---|---|---|
| `poteto-mode-sticky`, `short-prompt-continues-in-context` | claude-code | `relay-s27_4et8` | KNOWN | The baseline's borderline row recurred in 1 of 3 runs. Turn 1 recommended fast-forwarding `main`. On `/poteto-mode do it` the lead read `shipping.md` and ran `git merge --ff-only json-flag`. |
| `new-task-rematches` | claude-code | `relay-ulu4bu_1`, `relay-s27_4et8` | REAL | On "new task … don't change any code yet" the lead re-matched away from Opening a PR but chose Bug fix, not Investigation. `relay-s27_4et8` says "it uses the Bug fix playbook". The broken claim is the read-only pin in `docs/guide/02-poteto-mode.md`. The baseline and `2026-10-03.md` had Claude Code PASS. |
| `poteto-mode-reads-principles-and-names-applied` | claude-code | `tally-86yk3j_c` | KNOWN | The lead read three principle files and applied them without naming any. The other two runs named all three. |
| `reply-says-inconclusive-when-check-cannot-run` | claude-code | `tally-r_5omkox` | ORACLE | `reply_inconclusive` judges the whole command `… verify.py … \| tail -1; git diff … \| shasum`. The exit 127 came from `shasum`, and `verify.py` printed `ALL PASS`. |
| `worklist-opens-with-playbook-steps` | grok | `tally-1o8wftmc` | ORACLE | The worklist holds all eight steps. `item_matches_step` misses `**Step 8.** Run **Opening a PR**. State: pending.`, because `ITEM_NUMBER` does not match a `**Step 8.**` label and token overlap is 2 of 5. |

`read-only-phrase-pins-investigation` passed in `relay-ulu4bu_1` and `relay-s27_4et8`, and both PASSes are wrong. `read_only_pin` accepts `investigation.md` read anywhere in the turn, including as the second file of `cat bug-fix.md; echo ======; cat investigation.md` before the lead runs Bug fix.

In `relay-ulu4bu_1`, on turn 1 `continue`, the lead also acted on a turn-0 offer and rewrote both branch commits' author to the account identity. No promise grades this.

## Follow-ups

- Oracles: judge only the check segment of a compound command in `reply_inconclusive`; accept a `**Step N.**` label in `item_matches_step`; make `read_only_pin` require that the turn routes to Investigation, not only that it reads it.
- Skills: on "don't change any code yet", Claude Code chose Bug fix in 2 of 3 runs. Find what in the poteto-mode entry steers a defect report past the read-only pin.
- `sticky-followup` still leaves no open step after turn 0, which keeps its sticky verdict ambiguous.
