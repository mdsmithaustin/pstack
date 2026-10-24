# Claude Code rerun, 2026-10-24

## Examined revision

The live cases ran with `--skills-at d7ae91995a8b1aefab27658b8caefaaf90c0dd5b` (`d7ae9199`), `main` after #304. The evaluator was the same tree, which carries #307's ripgrep admission. Preflight admitted Claude Code `2.1.307` by signature (SHA-256 `5b113a7752119470f1da419cb0e608af3361cae25b614216b13022093958fb2a`). The commit that adds this report changes only this file.

## Changed live owners covered

The [eb4db2b receipt](2026-10-22-sync-eb4db2b.md) and the [e73df47 receipt](2026-10-24-sync-e73df47.md) left the Claude Code column unrun, because preflight refused the re-signed ripgrep that #307 now admits. This run covers the promises whose owners changed in #300, #297, and #304:

- `skills/poteto-help/SKILL.md` (#300, #297, #304). It owns `poteto-help-finds-need-and-routes`.
- `skills/setup-pstack/scripts/skill-listing.py` (#300, #297, #304). It owns `deslop-hands-unsettled-comments-to-no-comments`, `name-only-skills-stay-unloaded-unnamed`, `routed-skill-loads-after-compaction`, and `routed-skill-loads-when-named`.
- `skills/swarm/SKILL.md` (#304). It owns `swarm-fans-out-and-aggregates`, `swarm-returns-one-report-with-gaps`, `swarm-workers-report-pass-issues-blocked`, and `swarm-splits-verification-by-feature-map`.

`swarm-splits-verification-by-feature-map` is bound only to the deferred `verify-skill-run` case, so it did not run.

The seven bound cases ran once each on Claude Code with `evals/promises/live.py run`, in three batches: `poteto-help-run`, `poteto-help-unclear-run`, `name-only-unnamed-request`, `name-only-route-figure-it-out`, `name-only-route-after-compact`, `deslop-handoff`, and `swarm-run`. Every turn exited 0 without a timeout. `live.py report` rendered this matrix:

| promise | claude-code | codex | hermes | grok |
|---|---|---|---|---|
| `deslop-hands-unsettled-comments-to-no-comments` | PASS | not run | not run | not run |
| `name-only-skills-stay-unloaded-unnamed` | PASS | not run | not run | not run |
| `poteto-help-finds-need-and-routes` | PASS (2) | not run | not run | not run |
| `routed-skill-loads-after-compaction` | PASS | not run | not run | not run |
| `routed-skill-loads-when-named` | PASS | not run | not run | not run |
| `swarm-fans-out-and-aggregates` | PASS | not run | not run | not run |
| `swarm-returns-one-report-with-gaps` | INCONCLUSIVE (judge) | not run | not run | not run |
| `swarm-workers-report-pass-issues-blocked` | PASS | not run | not run | not run |

8 promises, 9 verdicts: PASS 8, INCONCLUSIVE 1. No grader refusal and no preflight error.

## Cases that did not run or need judgment

- **Codex, Hermes, and Grok, every case.** Out of scope for this rerun. The e73df47 receipt holds the current Codex rows. Grok needs the operator to run `grok login`, and the Hermes adapter fails on the local Hermes image.
- **`verify-skill-run`.** Deferred: it needs an app with a drivable surface and a multi-hour create-then-maintain run.
- **`swarm-returns-one-report-with-gaps`, run `kiln-vuz3gmm0`.** INCONCLUSIVE with `needs_judge`: the oracle found one reply covering all four packages, but it leaves compactness and gap reporting to a judge. Read by hand, the final reply is one table plus short sections, and it states the gap: no `check.sh` ran to completion, so every package is `BLOCKED`, and the direct `unittest` runs "are not runs of `check.sh`, so none of the four counts as a pass." That reading supports PASS, but the recorded verdict stays INCONCLUSIVE until a judge grades it.
- **Swarm statuses are all `BLOCKED` because of the run environment.** Each `check.sh` starts with `cd "$(dirname "$0")"`. Under the Claude Code adapter that call failed with `/bin/bash: dirname: command not found`, so the script ran from the repository root, found no tests, and exited 5. The `swarm-workers-report-pass-issues-blocked` PASS shows the lead reports statuses faithfully. It does not exercise a PASS or ISSUES status from `check.sh`.

## Comparison baseline

The newest earlier receipt is [the e73df47 sync receipt](2026-10-24-sync-e73df47.md). Its Claude Code column is "not run" throughout, as is the column in the receipt it names as its baseline, [the eb4db2b sync receipt](2026-10-22-sync-eb4db2b.md). So the newest Claude Code evidence comes from the receipts those two name in their Comparison baseline sections:

- [The 7a9a3ddb post-sync matrix](2026-10-20-sync-7a9a3ddb.md), the baseline the eb4db2b receipt names, has Claude Code PASS for `deslop-hands-unsettled-comments-to-no-comments`, `name-only-skills-stay-unloaded-unnamed`, `routed-skill-loads-after-compaction`, and `routed-skill-loads-when-named`, and PASS (2) for `poteto-help-finds-need-and-routes`. This run matches all five.
- [2026-10-03](2026-10-03.md), the swarm baseline the e73df47 receipt names, has Claude Code PASS for all three swarm promises. This run matches on `swarm-fans-out-and-aggregates` and `swarm-workers-report-pass-issues-blocked`. `swarm-returns-one-report-with-gaps` moves from PASS to INCONCLUSIVE, an oracle referral to the judge and not a FAIL. The hand reading above finds the gap reported.

No Claude Code verdict regressed to FAIL.
