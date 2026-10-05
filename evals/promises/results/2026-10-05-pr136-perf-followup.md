# PR136 performance live owner follow-up

**Status: ISSUES.** Execution is complete; this evidence does not support a full pass claim.

The performance playbook repair restores the critical-path net-benefit guard for added indirection. Its three bound live cases require a follow-up on all four harnesses. The architect files are unchanged from the first screen.

The acquisition contains one native trial for each of `route-perf`, `feature-run`, and `bug-fix-run` on Claude Code, Codex, Hermes, and Grok. Each harness ran its three cases sequentially in that order. All 12 were attempted once; no paid sample was retried. The existing native test suite and grade controls were not counted as samples.

Pins: evaluator commit `72e4a131aa7250c9624289367e4c2f44db27bc08`; skills commit `57e4409a6c4ebb7dfd27a5118caf478ef64bd769`. The evaluator checkout records `.github/upstream-sha` `23e4138daa01c42d4969f7a5465f82704e64f798`. The report matrix below used the candidate port's upstream commit `e43c7ee26e0038c6c1fa8380dd34ce86ff94cb2a` through `--upstream-ref`; it resolves in the evaluator checkout. The report command exited 0. Its failure signals were a nonzero exit, missing matrix totals, or a staged trial count other than 12.

## Trial outcomes

| Harness | Case | Native outcome | Frozen promise outcome | Evidence root |
|---|---|---|---|---|
| Claude Code | route-perf | Exit 1 after 6.8 s of 300 s; 401 expired OAuth token; no task work observed. | 1 INCONCLUSIVE | `.audit/pr136-live-followup/claude-code/route-perf/` |
| Claude Code | feature-run | Exit 1 after 4.7 s of 1800 s; same auth refusal; no task work observed. | 11 INCONCLUSIVE | `.audit/pr136-live-followup/claude-code/feature-run/` |
| Claude Code | bug-fix-run | Exit 1 after 6.5 s of 1800 s; same auth refusal; no task work observed. | 4 INCONCLUSIVE | `.audit/pr136-live-followup/claude-code/bug-fix-run/` |
| Codex | route-perf | Exit 0 after 252.3 s of 420 s; completed native turn. | 1 PASS | `.audit/pr136-live-followup/codex/route-perf/` |
| Codex | feature-run | Exit 0 after 779.1 s of 2400 s; completed native turn. | 5 PASS, 4 applicable INCONCLUSIVE, 2 NOT APPLICABLE | `.audit/pr136-live-followup/codex/feature-run/` |
| Codex | bug-fix-run | Exit 0 after 590.0 s of 2400 s; completed native turn. | 3 PASS, 1 frozen FAIL | `.audit/pr136-live-followup/codex/bug-fix-run/` |
| Hermes | route-perf | Timed out at 300 s; native exit -9; final reply empty. | 1 INCONCLUSIVE | `.audit/pr136-live-followup/hermes/route-perf/` |
| Hermes | feature-run | Exit 0 after 1744.3 s of 1800 s; transcript harvest refused with `path-refused`. | 11 INCONCLUSIVE | `.audit/pr136-live-followup/hermes/feature-run/` |
| Hermes | bug-fix-run | Exit 0 after 1494.1 s of 1800 s; transcript harvest refused with `path-refused`. | 4 INCONCLUSIVE | `.audit/pr136-live-followup/hermes/bug-fix-run/` |
| Grok | route-perf | Timed out at 300 s; native exit -9; partial turn. | 1 PASS for the routing oracle only | `.audit/pr136-live-followup/grok/route-perf/` |
| Grok | feature-run | Exit 0 after 1688.0 s of 1800 s; completed native turn. | 7 PASS, 3 applicable INCONCLUSIVE, 1 NOT APPLICABLE | `.audit/pr136-live-followup/grok/feature-run/` |
| Grok | bug-fix-run | Timed out at 1800 s; native exit -9; work stopped during design before implementation. | 2 PASS, 2 INCONCLUSIVE | `.audit/pr136-live-followup/grok/bug-fix-run/` |

The Claude Code traces contain only the prompt and repeated `401 OAuth access token has expired` errors; all three are attempts with zero task work. Hermes feature and bug fix traces contain native work, but the frozen evaluator returned INCONCLUSIVE for every promise because recorded reads crossed an unavailable fixture prefix. Their retained pairs were preserved and hash checked. Hermes route-perf timed out. Grok route-perf received a PASS only for routing before its native timeout, so it is not a completed task result.

Codex bug-fix retains the frozen FAIL for `reply-says-inconclusive-when-check-cannot-run`. The raw transcript later records a direct CLI reproduction with `CLI checks=10 failures=0` and a four test unittest discovery ending `OK`. The oracle evidence says its command matcher did not match the direct reproduction script against `-m\s+rollup`; the raw success does not alter the frozen grade. Grok feature has 11 raw promise entries and 10 applicable observations. Its three applicable INCONCLUSIVE grades concern matching reply text to the evaluator's 400-character output heads, an unexercised unavailable-check promise, and principle attribution that needs a judge. A separate Claude-only effort promise was not applicable. Grok bug-fix passed the route and pre-fix reproduction checks, then timed out before implementing a repair.

The retained Hermes exports are under `.audit/pr136-live-followup/hermes-retained/`. All three schema 2 pairs have no absent run records and every listed member matches its size and SHA-256: route-perf 385 members, feature-run 6,372, and bug-fix-run 6,372. Each pair retains 44 Hermes evidence files.

## Frozen evaluator report matrix

The report input contains one unchanged verdict file per trial and excludes retained Hermes copies. It contains 64 raw verdict entries; `live.py report` omits three `not_applicable` entries (two in Codex feature-run and one in Grok feature-run), leaving 61 applicable verdicts across 15 promises: 19 PASS, 1 FAIL, and 41 INCONCLUSIVE.

| promise | claude-code | codex | hermes | grok | upstream |
|---|---|---|---|---|---|
| `bug-fix-reproduces-before-fixing` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |
| `bug-fix-uses-poteto-tdd-when-cheap` | INCONCLUSIVE | PASS | INCONCLUSIVE | INCONCLUSIVE |  |
| `bug-prompt-routes-to-bug-fix` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |
| `claude-effort-applies-via-effort-agents` | INCONCLUSIVE |  | INCONCLUSIVE |  |  |
| `design-ladder-spares-small-changes` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |
| `perf-prompt-routes-to-perf-issue` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |
| `persona-delivery-hermes-grok` | INCONCLUSIVE |  | INCONCLUSIVE | PASS |  |
| `poteto-mode-reads-principles-and-names-applied` | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE |  |
| `poteto-mode-routes-to-playbook` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |
| `prove-it-works-checks-real-artifact` | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE | PASS |  |
| `reply-carries-commands-and-outputs` | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE |  |
| `reply-says-inconclusive-when-check-cannot-run` | INCONCLUSIVE (2) | FAIL 1, INCONCLUSIVE 1 | INCONCLUSIVE (2) | INCONCLUSIVE (2) | port |
| `skipped-step-stays-in-worklist` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |
| `worklist-in-native-task-tool` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |
| `worklist-opens-with-playbook-steps` | INCONCLUSIVE | PASS | INCONCLUSIVE | PASS |  |

15 promises, 61 verdicts: FAIL 1, INCONCLUSIVE 41, PASS 19

## Comparison baseline

The first screen remains historical at evaluator `e6c82e4015097a466f2922d4bcc864473145672e` and skills `933d2f8d683b807e4c7719aa534896caf9c7654e`. Its matrix reported 20 promises and 77 verdicts (8 FAIL, 31 INCONCLUSIVE, 38 PASS). Row comparisons here are descriptive only: evaluator and skills pins changed, this follow-up is not a paired baseline, and auth failures, timeouts, and harvest refusals limit several observations. No causal attribution is made.

`/correct` execution, Hillclimb, full performance experiments, and the effectiveness of the new architect red flags remain undriven by this follow-up.

All lane command/status records, traces, frozen verdicts, retained pairs, the report-input manifest, and the exact rendered matrix remain under `.audit/pr136-live-followup/`. The detached evaluator worktree is clean. No tracked source or documentation files were changed by this acquisition.
