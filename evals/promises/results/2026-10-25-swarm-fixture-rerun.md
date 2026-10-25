# Claude Code swarm-run rerun, 2026-10-25

## Examined revision

The case ran with `--skills-at 82bcfff9cc57ae30b2f5e0486d7049e96c5db049` (`82bcfff9`), the fix commit for #309 on the `fix/swarm-fixture-dirname` branch. Its `skills/` tree is byte-identical to `main` at `ee59a17a`. The branch changes only the `kiln` and `relay` fixture scripts and adds a test. The evaluator was the same tree, so the run used the fixed fixtures. Preflight admitted Claude Code `2.1.307` by signature (SHA-256 `5b113a7752119470f1da419cb0e608af3361cae25b614216b13022093958fb2a`).

## Why this rerun exists

In the [2026-10-24 Claude Code rerun](2026-10-24-claude-code-rerun.md), every `swarm-run` worker reported `BLOCKED`. Each `check.sh` started with `cd "$(dirname "$0")"`, and the Claude Code adapter's Seatbelt read allowlist denies `/usr/bin/dirname`. The scripts ran from the repository root, found no tests, and exited 5. The fixtures now strip the file name from `$0` in the shell and call no `dirname`. `relay/tools/old_callers.sh` had the same line, which made it print `0` instead of `3` under the sandbox. It now uses the same form. `NativeFixtureScripts` in `evals/promises/test_claude_code.py` runs each script inside and outside the sandbox and requires the same exit code and output.

## Matrix

`swarm-run` ran once on Claude Code with `evals/promises/live.py run --harness claude-code --case swarm-run`. The single turn exited 0 after 74.3 s, under the case's 1800 s cap, with `timed_out: false`. The trace has `x_evidence_complete: false`, because the lead started its four workers with `run_in_background: true`. No oracle reads that field. `live.py report` rendered this matrix:

| promise | claude-code | codex | hermes | grok |
|---|---|---|---|---|
| `swarm-fans-out-and-aggregates` | PASS | not run | not run | not run |
| `swarm-returns-one-report-with-gaps` | PASS | not run | not run | not run |
| `swarm-workers-report-pass-issues-blocked` | PASS | not run | not run | not run |

3 promises, 3 verdicts: PASS 3. No grader refusal and no preflight error.

Each worker ran `sh <worktree>/packages/<pkg>/check.sh` and reported the script's own result. `ingest`, `publish`, and `shape` exited 0 with `OK`. `render` exited 1 with `FAILED (failures=1)` on `test_columns_are_two_spaces_apart`. The oracle read the statuses `PASS`, `PASS`, `ISSUES`, and `PASS` from the lead's reply. These match an unconfined run of the same scripts. The lead's report names the gaps as "none" and gives the `render` cause.

## Cases that did not run or need judgment

- **Codex, Hermes, and Grok.** Out of scope. This rerun checks only the Claude Code fixture failure from #309. The fixture change does not depend on the harness.
- **`swarm-splits-verification-by-feature-map`.** Bound only to the deferred `verify-skill-run` case, so it did not run.
- **Sandbox noise the lead reported.** Every confined `sh` call printed `Error opening /private/var/select/sh: Operation not permitted` before its output. macOS `/bin/sh` reads that file to pick a shell and falls back when it cannot. The lead also found that the sandbox blocks `mktemp` and used Python's `tempfile.mkdtemp` instead. Neither changed an exit code or a verdict.

## Comparison baseline

The newest earlier receipt is [the 2026-10-24 Claude Code rerun](2026-10-24-claude-code-rerun.md). It has Claude Code PASS for `swarm-fans-out-and-aggregates` and `swarm-workers-report-pass-issues-blocked`, and INCONCLUSIVE (judge) for `swarm-returns-one-report-with-gaps`. This run matches on the first two. Here they rest on real `PASS` and `ISSUES` statuses, not four `BLOCKED` ones. `swarm-returns-one-report-with-gaps` moves from INCONCLUSIVE to PASS, because this reply names its gaps in words the oracle matches. Before the sandbox (#138), the [2026-10-03](2026-10-03.md) screen had Claude Code PASS for all three swarm promises. This run matches it on all three.

No Claude Code verdict regressed.
