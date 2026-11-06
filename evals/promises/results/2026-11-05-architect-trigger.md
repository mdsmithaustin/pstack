# Narrower architect trigger, 2026-11-05

This receipt covers the #425 change. The architect trigger in `task-triggers.md` and Feature step 2 now fires only when a change crosses two or more source files and admits several plausible shapes, and arena's Pick waits for the cross-judge's verdict.

**The one-module case shows no separation.** `feature-one-module-run` asks for a two-function `--pairs` option on the one-module `tally` fixture. Every lead skipped the design fan-out under both the old and the new text, so the case guards the skip but cannot show fewer comparisons on this model. A `--format` pilot with several plausible shapes also skipped the fan-out under the old text in 2 of 2 runs.

**The cross-module guard fails before and after the change.** `feature-boundary-run` fanned out in no run under either text. Under the old text, both leads loaded `architect` and then skipped the fan-out. Under the new text, no lead loaded it, and only 1 of 3 recorded a skip, because Feature step 2 then gave a skip only to a small, self-contained change. With the skip clause extended to a change with a single plausible shape, 2 of 2 leads recorded the skip. #439 tracks the guard.

**The architect run waited for the judge.** In `architect-run` at the new text, the lead spawned the cross-judge after all three runners finished, waited for its completion notice, and made its first graft write after it. It picked the judge's top base and recorded the deciding criterion. The trace carries no judge-completion event, so this order was read by hand from the lead transcript. #432 tracks an oracle for it.

## What ran

- Harness: Claude Code with `claude-sonnet-5-5` at effort high. Command per arm: `python3.14 evals/promises/live.py run --harness claude-code --model claude-sonnet-5-5 --effort high --skills-at <pin> --runs <n> --case <case> --out <dir>`. The arms ran in parallel, and the runs inside an arm ran in sequence. No run was retried.
- Old text: `d9a615d3`, trunk before the change. New text: `c07e0fd5`. A later commit on the branch changes the Perf issue and Refactoring architect steps, which these Feature cases do not reach.
- Variant: `91e05bde`, an unpublished commit that added "even if you already favor one" to the trigger and Feature step 2. The branch does not keep it.
- Skip clause: `b5dd45b9`, an unpublished commit on `027f6e41` with the branch's final Feature step 2 and arena text. Its `feature-one-module-run` bound the routing and real-artifact checks but ran with the task tools off. The committed case turns them on, as `feature-run` does.
- The `--format` pilot was an unpublished case with the turn `add a --format option that prints the counts as text, csv, or json. text stays the default and byte-identical. verify all three.` on `tally`, graded by `design-ladder-spares-small-changes`.

## Results

| case | old text | new text | variant | skip clause |
|---|---|---|---|---|
| `feature-one-module-run`, no fan-out | 2 of 2 | 2 of 2 | 2 of 2 | 2 of 2 |
| `feature-one-module-run`, real artifact checked | not graded | not graded | not graded | 2 of 2 |
| `feature-one-module-run`, routed to Feature | not graded | not graded | not graded | 1 of 2, 1 inconclusive |
| `--format` pilot, no fan-out | 2 of 2 | not run | not run | not run |
| `feature-boundary-run`, fan-out | 0 of 2 | 0 of 3 | 0 of 2 | 0 of 2 |
| `feature-boundary-run`, step 2 skip recorded | 2 of 2 | 1 of 3 | 1 of 2 | 2 of 2 |
| `architect-run`, all promises PASS | not run | 1 of 1 | not run | not run |

Run ids, from each run's `verdict.json`:

- Old text: `tally-nsodkzlg`, `tally-os0xktqw`, `tally-_cl_bf95`, `tally-tvgerug7`, `relay-rm2tp_6u`, `relay-hqgtip8s`.
- New text: `tally-gz6fahwy`, `tally-jzhd0y8o`, `relay-pfhsjn3q`, `relay-49dq0wjf`, `relay-jwlj2n22`, `relay-875bkqqc`.
- Variant: `tally-rp4p_m65`, `tally-vsjtiuqw`, `relay-z2jezhcf`, `relay-xbl5h25q`.
- Skip clause: `tally-ingpuej1`, `tally-kgq3vt9_`, `relay-htl9skml`, `relay-l_hjmqy4`.

Skip reasons the leads wrote for `feature-boundary-run`:

- Old text: `skipped: ~60-line change, one natural shape reusing Record/Store/retry; an arena bakeoff costs more than the decision`, and "skipped: step 2, `architect` (small change confined to one retry path; I compared two shapes inline)".
- New text: `skipped (one call chain; the only open choice was where the int rides)`. A second lead left the step pending and gave its reason only in the final reply: "I had already read the whole 295-line subsystem and the shape was clear." The third recorded no reason.
- Variant: "The change is about 50 lines in one package" and "every edit was small".
- Skip clause: `skipped: single plausible shape` and "skipped: one dominant shape".

## Limits

- One harness and one model. Codex, Hermes, and Grok Build did not run these cases with the new text.
- Two or three runs per cell cannot show a rate. The one-module rows match across arms, so they say nothing about the change.
- These runs did not exercise the judge send-back or the override record. In the one architect run, the judge recommended its top scorer and the lead agreed with it. PR #440's verification records the gate runs that exercised both.
