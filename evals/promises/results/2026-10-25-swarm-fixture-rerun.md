# Claude Code swarm-run rerun, 2026-10-25

## Examined revision

The case ran with `--skills-at 82bcfff9cc57ae30b2f5e0486d7049e96c5db049` (`82bcfff9`), the fix commit for #309 on the `fix/swarm-fixture-dirname` branch. A squash merge drops that SHA, so two trees identify the run. Its `skills/` tree is byte-identical to `main` at `ee59a17a`. Its `evals/promises/fixtures` tree is `48c4d01a17718881677a411d917ce782e572db00`, which the merged change keeps. That commit differs from `ee59a17a` only in the `kiln` and `relay` fixture scripts and one test. The evaluator was the same tree, so the run used the fixed fixtures. Preflight admitted Claude Code `2.1.307` by signature (SHA-256 `5b113a7752119470f1da419cb0e608af3361cae25b614216b13022093958fb2a`).

## Why this rerun exists

In the [2026-10-24 Claude Code rerun](2026-10-24-claude-code-rerun.md), every `swarm-run` worker reported `BLOCKED`. Each `check.sh` started with `cd "$(dirname "$0")"`, and the Claude Code adapter's Seatbelt read allowlist denied `/usr/bin/dirname` at that revision. The scripts ran from the repository root, found no tests, and exited 5. `relay/tools/old_callers.sh` started with `cd "$(dirname "$0")/.."`, so under the sandbox it ran from `/` and printed `0` instead of `3`. All five scripts now strip the file name from `$0` in the shell and call no `dirname`. `NativeFixtureScripts` in `evals/promises/test_claude_code.py` runs every fixture script by absolute path and by bare name, inside and outside the sandbox. It requires each script's known exit code, stdout, and unittest summary.

## Matrix

`swarm-run` ran once on Claude Code with `evals/promises/live.py run --harness claude-code --case swarm-run`, as run `kiln-xhw5yunx`. The lead ran on `claude-opus-5-5` at `high` effort, and its four workers ran on `sonnet`. The single turn exited 0 after 74.3 s, under the case's 1800 s cap, with `timed_out: false`. The trace has `x_evidence_complete: false`, because the lead started its workers with `run_in_background: true`. No oracle reads that field. `live.py report` rendered this matrix:

| promise | claude-code | codex | hermes | grok |
|---|---|---|---|---|
| `swarm-fans-out-and-aggregates` | PASS | not run | not run | not run |
| `swarm-returns-one-report-with-gaps` | PASS | not run | not run | not run |
| `swarm-workers-report-pass-issues-blocked` | PASS | not run | not run | not run |

3 promises, 3 verdicts: PASS 3. No grader refusal and no preflight error.

Each worker ran `sh <worktree>/packages/<pkg>/check.sh` and reported the script's own result. `ingest`, `publish`, and `shape` exited 0 with `OK`. `render` exited 1 with `FAILED (failures=1)` on `test_columns_are_two_spaces_apart`. These are the results `NativeFixtureScripts` expects from the scripts both inside and outside the sandbox. The oracle read the statuses `PASS`, `PASS`, `ISSUES`, and `PASS` from the lead's reply.

## Cases that did not run or need judgment

- **Codex, Hermes, and Grok.** Out of scope. This rerun checks only the Claude Code fixture failure from #309. The fixture change does not depend on the harness.
- **`swarm-splits-verification-by-feature-map`.** Bound only to the deferred `verify-skill-run` case, so it did not run.
- **Sandbox denials outside the fixtures.** The lead's own commands hit tools the policy did not grant at this revision. Its `mktemp -d` exited 127, so it made its worktree directories with Python's `tempfile.mkdtemp`. `skills/pstack-harness/references/delegation.md` tells agents to use `mktemp -d` for throwaway checkouts. Its cleanup printed `dirname: command not found` and `rmdir: command not found`. `skills/pstack-harness/references/portable-paths.md` also calls `dirname`. The fixture fix did not address these skill commands. The subsequent fix for #316 admits the tools; see the current [Claude Code isolation policy](../README.md#native-parent-grading-boundary). Every confined `sh` call also printed `Error opening /private/var/select/sh: Operation not permitted` before running the script. None of these changed a worker's exit code or a verdict.
- **Relay cases now see the real count.** `old_callers.sh` printed `0` under the Claude Code sandbox from #138 (merged 2026-10-04) until this change, and now prints `3`. The 2026-10-24 rerun measured its three `name-only-*` relay rows against the broken script. Each lead ran it and got `0`, and two committed "Make old_callers.sh fail loudly instead of reporting a false zero." Their PASS verdicts stand, because no oracle reads that count. The two `routed-skill-*` verdicts cite the `figure-it-out` load at sequence 8, and the `name-only-skills-stay-unloaded-unnamed` verdict finds no name-only skill load. Those rows were not rerun after this change.

## Comparison baseline

The newest earlier receipt is [the 2026-10-24 Claude Code rerun](2026-10-24-claude-code-rerun.md). It has Claude Code PASS for `swarm-fans-out-and-aggregates` and `swarm-workers-report-pass-issues-blocked`, and INCONCLUSIVE (judge) for `swarm-returns-one-report-with-gaps`. This run matches on the first two. Here they rest on real `PASS` and `ISSUES` statuses, not four `BLOCKED` ones.

`swarm-returns-one-report-with-gaps` moves from INCONCLUSIVE to PASS, but the PASS is weak evidence for gap reporting. This run had no gaps, because every worker returned a result. The oracle's gap pattern first matched the reply's "Gaps and notes" heading, whose section says "Gaps: none." The 2026-10-24 reply reported a real gap in words the oracle did not match. With the fixed fixtures, `swarm-run` no longer produces a missing or blocked package, so reporting a real gap stays unmeasured on Claude Code.

The [2026-10-03](2026-10-03.md) screen had Claude Code PASS for all three swarm promises. That file says its matrix is not a post-fix baseline, and `skills/swarm/SKILL.md` has changed since, in #304 among others. Its rows are context, not a baseline.

No Claude Code verdict regressed.
