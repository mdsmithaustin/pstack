# Upstream sync 0b46ec3 cut screens, 2026-11-25

PR #575 syncs upstream `c742dd61..0b46ec39`. It adopts each upstream cut and each port-owned trim unless a paired screen proves the rule it removes is needed. A cut is adopted by default and kept only on proof.

This receipt records the method, the decision per screen, what the PR applied, the run accounting, the departures from the filed protocol, the grader defects, and every counted cell.

## Method

### Arms

Each screen compares a base arm with a cut arm on the same cases. Arm A is the base for S and H screens. Arm A2 is the base for X screens. The cut arm is B, with two exceptions. S6-orch has two cut arms, B1 (orch-agentic) and B2 (orch-delete). H-agentmodel ran a probe arm, P, beside the base.

Every arm is a WIP ref on origin under `refs/pstack/wip/sync-575/`. Arm A is `1b4fcd0f` (`arm-adopt`) and arm A2 is `d4d4476f` (`arm-a2`). Each cut arm has its own ref under the same prefix. Only `skills/` comes from the arm.

Cases, fixtures, histories, the forge double, and graders came from one run checkout for every arm. The filed checkout was `2c030b3b`, the WIP ref `screen-harness-x`. The runs used that commit plus one `live.py` option, `--workspace-models`, and its unit test (operator decision 3 below). Cases, fixtures, histories, the forge double, and graders are byte-identical to `2c030b3b`.

### Leads

A lead is one harness and model pair.

| Label | Lead |
|---|---|
| CC | `--harness claude-code --model claude-sonnet-5-5 --effort high` |
| CX | `--harness codex --model gpt-6.2-sol --effort high` |

Each run was `python3 evals/promises/live.py run <lead> --case <case> --skills-at <arm sha> --out <dir>` from the run checkout. Delegates a lead spawns, on any model, belong to its arm. The runs record each spawn's model and effort as a measure. No run was voided, excluded, or reweighted for a delegate's model.

### Counting rules

The screen index and one rule per screen were filed on 2026-11-24, before the first screen run. A rule that states its own version of a protocol item overrides that item for its screen only.

**Signals (P1).** Each rule sorts the signals it reads into four kinds. A decision signal is a grader promise or a computed signal tied to named rows. Only a decision signal can prove a row needed. A guard signal is read and reported but never decides. A guard that meets the margin is reported as an unattributed regression, and the adopt default still stands. A measure is recorded and is never a verdict. Excluded signals are never counted. Routing promises are always excluded (issue #590), and so is any promise whose FAIL condition is the absence of the exact mechanism the cut removes.

**Verdicts (P2).** Each decision signal gets one verdict per run, PASS, FAIL, or INCONCLUSIVE. The automatic verdict comes from the oracle or from the computed signal the rule defines. A blind checker then reads each FAIL's cited evidence against the trace. A FAIL whose evidence is absent from the trace or contradicted by it is a grader defect, and it becomes INCONCLUSIVE. A blind reader may turn an INCONCLUSIVE into PASS or FAIL only from an excerpt type the rule names, and only by that rule's rubric. A reader never changes an automatic PASS or FAIL. INCONCLUSIVE never counts as a pass or a fail.

**Margin rule (P3).** For each decision signal and each lead, `F_arm` is the number of that arm's runs whose verdict is FAIL. A signal proves its rows needed on a lead when `F_cut - F_base >= 2` with 3 runs per arm. The cut arm then fails in at least 2 more of the 3 runs than the base arm. Each lead is judged on its own, and one lead meeting the margin is proof. A signal that meets the margin keeps only the rows its rule maps to it, and every other row of the screen is adopted. When a signal maps to several rows the screen cannot separate, all of them are kept. A decision signal with 2 or more INCONCLUSIVE runs on both arms of a lead is unmeasured on that lead. Unmeasured means adopt.

**Staged runs (P4).** Each case and lead pair first ran 2 runs per arm. After stage 1 was graded, FAIL-checked, and read, the pair got a third run per arm only when some decision signal on it had `F_cut - F_base >= 1`. When every decision signal was at 0 or below, no third run could reach the margin, so the pair stopped and its signals settled as not proven. The pooled X26 routes and the H-agentmodel probe were not staged.

**Void runs (P5).** A run is void when it has no verdict, when every applicable verdict is ERROR, when the grader reports that it never started or could not read its transcript, when host skills touched it, or when it fails a validity check its rule names. A void run is rerun once on the same arm, case, and lead. A void rerun counts as INCONCLUSIVE on every signal. A run that timed out after doing work is not void, and its verdicts stand as graded.

**Blinding (P6).** Every run directory had a random token for a name. One sealed file mapped tokens to arms, and only the scheduler and the counting script read it. Arms of the same pair ran in the same wave in random interleaved order, so time-of-day and service drift fell on both arms. The computed-signal scripts were written before the map was opened and ran over every run of both arms. Readers saw only the excerpt the rule names, keyed by token and shuffled across arms within a batch. A run's excerpts went to a reader from the other model family, at high effort. Before a rubric's first batch, the reader labeled two synthetic excerpts, one PASS and one FAIL. A reader that mislabeled either one did not read that rubric.

### Operator decisions before the first run

1. **Not run, adopted unscreened.** S2 (rows 2, 5, 8, 9, 13), the seeded half of X14 (M99, M103, M120, L87, and their controls), and X3's L10 card. Those cuts are adopted without a screen.
2. **H-models and H-swarm ran on both harnesses.** Each of their runs, on both arms and both leads, launched with `live.py run --workspace-models`. That option copies the arm's own `skills/setup-pstack/examples/pstack-models.md` into the run project's `.agents/pstack-models.md` and excludes it from git. The resolver ranks that copy's `## claude-code` and `## codex` sections above every line of the operator's user-level file. A smoke run checked that every role resolves from the workspace layer with the arm's values while the real user file is in place. This check replaced the private-HOME validity checks in the H-models and H-swarm rules. The operator's file was never edited or moved.
3. **Run checkout.** The run checkout is `2c030b3b` plus the `--workspace-models` option and its unit test.
4. **Leads.** Every run passes `--effort high` with the lead model in the table above.

The run was unattended. Where a rule or P6 sends a rubric to the operator, that rubric's INCONCLUSIVE verdicts stayed INCONCLUSIVE.

## Decisions

The decision script computed this table from the adjudicated verdicts. Adopted rows have the cut applied. Kept rows keep the port's text because a screen proved the rule needed. The Basis column names the signal, case, and lead behind a keep, or says why the screen adopted.

| Screen | Adopted (cut applied) | Kept (rule proven needed) | Basis |
|---|---|---|---|
| S1 | 6, 21, 30, 32, 41 | - | no decision signal met the margin |
| S3 | 15, 16, 25 | - | no decision signal met the margin |
| S4 | 23 (AskQuestion and full-autonomy lines) | - | no decision signal met the margin |
| X1 | U3, U5, AU2 | - | no decision signal met the margin |
| S5 | 20 | 29, 31, 33, 34, 36 | how-why-reports-name-sources-searched [why-run] CC; how-why-reports-name-sources-searched [why-run] CX |
| X16 | L19, L49, L52 | - | no decision signal met the margin |
| S6-plan | 19 | - | no decision signal met the margin |
| X5 | O36, O9, O12, O19, O34 | - | no decision signal met the margin |
| S6-orch | 28 as orch-delete (upstream #1249) | - | orch-delete not proven to fail by the margin; deleting the orch code stays the operator's call |
| H-pr | 17 | - | no decision signal met the margin |
| H-babysit | 18 | - | no decision signal met the margin |
| H-playbooks | 27 (all but the kept text) | 27 (playbook descriptions and step-away sentences) | H-playbooks-stepaway [route-going-to-bed] CX |
| H-smyw | 37 | - | no decision signal met the margin |
| H-swarm | 38 | - | no decision signal met the margin; cost swarm-run CC: median ratio 1.49, every B above max A: True, rule met: False; cost swarm-run CX: INCONCLUSIVE (a run has no recorded cost) |
| H-models | - | 42, 43 | arena-lead-reads-rationales-and-base [arena-run] CC; cost arena-run CC: median ratio 0.77, every B above max A: False, rule met: False; cost arena-run CX: INCONCLUSIVE (a run has no recorded cost); cost feature-run CC: median ratio 0.54, every B above max A: False, rule met: False; cost feature-run CX: INCONCLUSIVE (a run has no recorded cost); guard met the margin (unattributed regression, adopt stands): worklist-opens-with-playbook-steps [feature-run] CX |
| H-agentmodel | - | 44 | probe: CC pin overridden (both probe leads passed model sonnet on the call; children ran claude-sonnet-5-5; effort pin applied only where the call omitted effort); CX pin reaches the child (probe children gpt-6-sol@xhigh, base children gpt-6.2-sol@high, no call override) |
| X2 | O8, O39, O42, L40, H68, SH4, M46 | M10 | x2-failed-plan-worklist-from-playbook [x2-plan-script-broken] CX; x2-failed-plan-worklist-opens-with-steps [x2-plan-script-broken] CC |
| X3 | L3, L6, L7, L8, L9, L10, L51, L80, O37, M34 | - | no decision signal met the margin |
| X4 | O53, O58, H12, H13, H14, AF5, M79 | - | no decision signal met the margin |
| X6 | P5, P6, P20 | - | no decision signal met the margin |
| X7 | SH5, M48, M48b | B2 | x7-docs-pending-before-merge-ready [x7-babysit-undocumented-rename] CC |
| X8 | B15, B6 | - | no decision signal met the margin |
| X9 | AF7, AF9, AF16 | - | no decision signal met the margin |
| X11 | L30, L31, L32, L44, H10, H17, H21, H23, H28 | - | no decision signal met the margin |
| X12 | H36, H39, L16, L41, M52, L56, L58, M81, M87, M117 | - | no decision signal met the margin |
| X13 | L12, L64, L68, L92, M32, M36 | - | no decision signal met the margin |
| X14 | L33, L87, M32b, M99, M100, M101, M103, M118, M119, M120 | - | no decision signal met the margin |
| X15 | L18, L45 | M56b | X15-trail [overnight-run] CC |
| X17 | L83, L84, L93 | L26, L82 | x17-subjective-criterion-calibrated [x17-subjective-criterion] CX |
| X18 | L36, L37 | L34, L35 | how-explains-current-code [how-wide-run] CC |
| X20 | L78, L91 | - | no decision signal met the margin |
| X21 | H84, H88, M64 | - | no decision signal met the margin |
| X22 | H9 | - | no decision signal met the margin |
| X23 | - | M93, O16 | x23-writer-worktree-removed [x23-writer-delegate-cleanup] CC |
| X24 | O84, O87 | O70 | x24-setup-lists-efforts-before-claude-install [x24-setup-scripted] CX |
| X25 | M1, M24 | - | no decision signal met the margin |
| X26 | - | M18, M22 | X26-route [pooled 7 routes] CC |
| X27 | M72 | - | no decision signal met the margin |
| X28 | M77 | M78 | X28-announce [feature-run-no-todo] CC |
| X29 | M92, M105 | - | no decision signal met the margin |
| S2 | 2, 5, 8, 9, 13 | - | operator decision 1: not run, adopted unscreened |
| X14 seeded half | M99, M103 (seeded card), M120, L87 | - | operator decision 1: not run, adopted unscreened |
| X3 L10 card | L10 | - | operator decision 1: not run, adopted unscreened |

### Notes on the decisions

- S6-orch adopted orch-delete, so X2's O8 is moot under its rule. The screen left the deletion of the orch code to the operator.
- S5 keeps rows 29 and 31, because how-why-reports-name-sources-searched met the margin on both leads. By its rule, rows 33, 34, and 36 follow 31. Row 20 is adopted. Row 31 is kept, so `epistemics.md` does not move.
- H-agentmodel keeps the hold on row 44. On Claude Code the call's `model: sonnet` overrode the pinned persona model. On Codex the pin reached the child.
- H-models keeps rows 42 and 43 on arena-lead-reads-rationales-and-base CC. Its cost rule was not met on any lead. The CC ratios were below 1.5, and CX cost is INCONCLUSIVE because the trace records no subagent token usage. One guard, worklist-opens-with-playbook-steps on feature-run CX, met the margin. It is reported as an unattributed regression, and the default stands.
- H-swarm adopts row 38. The CC cost ratio is 1.49 with every B run above the most expensive A run. The rule needs a ratio of at least 1.5, so it is not met. CX cost is INCONCLUSIVE for the same reason as H-models.
- X2 keeps M10 only, on worklist-from-playbook CX and worklist-opens-with-steps CC. O39 is effectively unmeasured on CX. Both x2-plan-check-no-node launches were void because a JS runtime ran despite the stripped PATH.
- The H-smyw and X11 rules assume Claude Code runs read the operator's user-level `pstack-models.md`. The Claude Code adapter's Seatbelt policy grants no read of that file's directory, so whether those runs saw the file is unverified. The H-models and H-swarm runs did not depend on it. They used the workspace layer, which the smoke run confirmed.

## What landed

- PR #575 applies the Adopted rows from their arms and keeps the port's text for the Kept rows, with the exceptions below.
- S5 applies only row 20, the reflect single-agent rewrite. Rows 29, 31, 33, 34, and 36 (how, why, recall, blast-radius, teach) keep the port text.
- H-playbooks applies only the drop of the entry's `skipped: <reason>` record clause and its reason-content sentence. The playbook descriptions, `references/playbooks.md`, and the step-away figure-it-out sentences keep the port text.
- H-models rows 42 and 43 and H-agentmodel row 44 keep the port text.
- S6-orch is applied as the deletion of Orchestrate, its scripts, and its tests, by operator decision. Program-scale work routes to figure-it-out. The deletion makes X5's O9, O12, O19, and O34 and X2's O8 moot. X5 applies O36.
- X23 keeps M93. Its kept O16 sat in the Orchestrate playbook, which the PR deletes.
- S2, the seeded half of X14, and X3's L10 are adopted unscreened, by operator decision 1.
- The 129 confirmed trims in arm A2, the X screens' base, are in.
- X10 (gated publish GP7, GP15, GP16, GP18, GP20) and X19 (why `-R`, L39): not screened, no fixture; port text kept. X10 needs a provisioned gate and X19 a fork with an `upstream` remote. Both rules guard real failures, an ungated publish and the wrong repository on a fork, and the operator adopted only S2, the seeded half of X14, and X3's L10 unscreened.

## Run accounting

- The manifest has 610 rows. They are 512 stage-1 runs (260 CC, 252 CX, as filed), 46 stage-2 runs, and 52 reruns of void runs.
- Void runs (P5) were not counted. The adjudication log has 53 void entries.
  - 50 Claude Code runs ended inside the usage-limit window, 2026-11-24 23:12:30 to 23:16:50Z, with "You've hit your..." in their output. The CLI exited 0. 47 graded as "run never started" and 3 did partial work. Each was rerun once, on the coordinator's instruction, because a limit-window run is not an attempt.
  - 1 grade refusal. The X11 interrogate-run CC grade was refused (`unsafe_root`) because an arena candidate worktree sat inside the run's temporary directory, so the run has no verdict. That run was itself a limit rerun, so it got its single real rerun, which counted.
  - 1 X2 validity void. A JS runtime ran in x2-plan-check-no-node CX. Its rerun ran one too, so it counts INCONCLUSIVE on every signal (P5).
- Stage 2 (P4) continued on the pairs below. Every other pair stopped at stage 1.

| Screen | Pairs that ran stage 2 |
|---|---|
| H-models | arena-run CC |
| H-playbooks | feature-plan-route-run CX, route-going-to-bed CX |
| H-swarm | swarm-run CC (cost trigger) |
| S1 | feature-boundary-run CC and CX |
| S4 | fork-cache-policy-run CC |
| S5 | how-wide-run CC, why-run CC and CX |
| X15 | overnight-run CC |
| X17 | x17-subjective-criterion CX |
| X18 | how-wide-run CC |
| X2 | x2-plan-script-broken CC and CX |
| X22 | x22-dirty-checkout-review CC |
| X23 | x23-writer-delegate-cleanup CC |
| X24 | x24-setup-scripted CX |
| X25 | sticky-followup CC and CX |
| X28 | feature-run-no-todo CC |
| X7 | x7-babysit-undocumented-rename CC |
| X9 | x9-root-lane-reports CC |

## Adjudication

- **FAIL check (P2.2).** 178 blind checks ran, one sonnet checker per FAIL. Each checker saw only the trace, the project copy, and the claim. The checkers judged 56 FAILs grader defects, and those turned INCONCLUSIVE. Four pr-calls-name-repo FAILs were rechecked after the checker brief was clarified to name the forge call log, and all four were confirmed.
- **Readers (P2.3, P6).** 72 batches ran. Codex `gpt-6.2-sol` at high effort read CC runs, and Claude `opus` at high effort read CX runs. Each batch carried two synthetic items. 7 calibrations failed. 6 failed on flawed synthetics the runner wrote, and in each the reader's label was defensible. The runner fixed those synthetics and reread each of those batches whole with a fresh reader. All 6 rereads calibrated. The seventh was a rubric that never gives FAIL. Its negative synthetic now expects CANNOT_TELL, and no label changed. CANNOT_TELL leaves INCONCLUSIVE. 52 INCONCLUSIVE items carry no excerpt type their rule names and were not read.
- **Frozen scripts.** The scoring scripts were hashed before any count. Later edits were tooling only, namely the excerpt wiring, the rubric synthetics, the dedupe of plan items, and the cost-list fix that skips replaced void runs. No rule was edited after the first run.

### FAIL re-check (v2, 2026-11-25)

The first FAIL check turned 56 FAILs INCONCLUSIVE. An audit then found its claims incomplete (departure 4). Two fresh blind checkers on different models, fable and sonnet, re-checked each of the 56. Each checker got a fixed claim. It quoted the FAIL meaning from the rule and gave the turn index the signal reads, from 0. It also carried the grader's failures, or the cited evidence for computed signals, and the turn prompts. A conversion stays INCONCLUSIVE only when both checkers say "grader defect". Otherwise the FAIL is restored.

The same dual check, under the same rule, ran on three confirmed FAILs the audit named as peers. One is on X17 and two are on skipped-step-stays-in-worklist. It also ran on the two FAILs of the H-models guard that met the margin (worklist-opens-with-playbook-steps, feature-run CX), which the first check had skipped. The scripts were hashed again before this re-check. The re-check covered 61 items. The two checkers agreed on 90% of them, and 17 conversions were restored to FAIL.

## Departures from the filed protocol

Each departure was made during the run and is recorded in the adjudication log. None changes a filed rule.

1. **P6 calibration rereads.** P6 says a reader that mislabels a synthetic item does not read that rubric, and the operator reads it instead. Six batches failed calibration because the runner's synthetic examples were weak. In each, the reader's label on the synthetic was defensible under the rubric. The runner fixed those synthetics and reread the whole batch with a fresh reader of the same family, instead of leaving the items INCONCLUSIVE. The six batches were how-facts CC, S1-structure CC, S1-structure CX, X16-lever CC, X1-request CC, and x23-worktree CC. Separately, the plan-only-no-doc CX batch was re-scored after its negative synthetic was relabeled CANNOT_TELL, because that rubric never gives FAIL. No label changed there.
2. **Three voided partial-work runs.** P5 says a run that did work is not void. Three Claude Code stage-1 runs did partial work before the usage limit cut them off. Two were X17 runs on x17-subjective-criterion, and one was an X20 run on feature-one-module-run. The grader did not mark them void. The runner voided them on the coordinator's instruction to void every run that hit an API or rate-limit error, and reran each once.
3. **X11's second rerun.** P5 allows one rerun of a void run. An X11 interrogate-run CC run was itself the rerun of a usage-limit void, and its grade was then refused (`unsafe_root`). The runner treated the limit-window run as not an attempt and gave it one more rerun, which counted.
4. **Empty claim fields in the first FAIL check.** The first-round checker claims did not state the signal's FAIL meaning or the turn the signal reads. For computed signals, `failures` was empty, and the cited text sat only in `evidence`. An independent audit found 5 of 13 sampled conversions wrong, including two checks that read the wrong turn. So every first-round conversion (56) was re-checked, as the FAIL re-check above describes. The four pr-calls-name-repo FAILs had also been rechecked mid-run, after the checker brief was clarified to name the forge call log. Those were confirmed then.
5. **Smaller items.** One checker's result file had a broken escape, which the runner repaired. The result was unchanged. From wave 6 on, each wave's blind checks and reader batches ran inside one runner delegate per wave, with the same roles and models. The runner wrote the rubric reason filters from the rules' named excerpt types. A sweep found that the 52 unmatched INCONCLUSIVE items carry no named type.

## Grader defects

A blind checker found the FAILs of these signals absent from or contradicted by the trace. Issue #598 files them.

| Signal | FAILs |
|---|---|
| why-reports-null-results | 9 |
| why-reports-cited-history | 6 |
| show-me-your-work-spawns-trail-reviewer (Codex trail-reviewer `spawn_agent` present before the reply) | 6 |
| skipped-step-stays-in-worklist | 4 |
| X25-readonly | 4 |
| worklist-follows-plan-and-is-kept | 3 |
| arena-lead-reads-rationales-and-base | 3 |
| X14-scrutiny | 3 |
| x9-root-fix-forward-holds-reached-finding | 3 |
| lead-prints-plan-before-edits | 2 |
| x9-root-quota-is-not-a-lane-failure | 2 |
| x9-root-records-base-finding | 2 |
| X26-route | 1 |
| documentation-impact-modes-invocable | 1 |
| x17-subjective-criterion-calibrated | 1 |
| poteto-runs-documentation-impact-before-completion | 1 |
| x22-review-leaves-dirty-checkout-unchanged | 1 |
| X15-trail | 1 |
| arena-fans-out-and-grafts | 1 |
| x9-root-files-invented-input-finding | 1 |
| plan-step-loads-arrive-with-step | 1 |

The runner noticed one more problem while building the computed signals. After a `cd` into `$TMPDIR`, a shell write resolves inside the project and is classed as a source edit.

## Cells

A cell is one signal, case, and lead. Counts are PASS/FAIL/INCONCLUSIVE, with the run count in parentheses. In the Base column, A is each screen's base, which is arm A2 for X screens. The Cut column names the cut arm. PROVEN marks a cell that met the margin. Unmeasured marks a cell with 2 or more INCONCLUSIVE runs on both arms, which means adopt (P3). H-agentmodel was a probe and has no cell table.

### S1

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| S1-shape [feature-boundary-run] CC | decision | B | A 0/2/1 (3) | B 1/2/0 (3) | +0 | not proven |
| S1-shape [feature-boundary-run] CX | decision | B | A 0/3/0 (3) | B 1/2/0 (3) | -1 | not proven |
| S1-structure [feature-boundary-run] CC | decision | B | A 1/2/0 (3) | B 0/3/0 (3) | +1 | not proven |
| S1-structure [feature-boundary-run] CX | decision | B | A 2/1/0 (3) | B 1/2/0 (3) | +1 | not proven |
| S1-grounding [feature-boundary-run] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| S1-grounding [feature-boundary-run] CX | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| design-ladder-spares-small-changes [feature-one-module-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| design-ladder-spares-small-changes [feature-one-module-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| prove-it-works-checks-real-artifact [feature-one-module-run] CC | guard | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| prove-it-works-checks-real-artifact [feature-one-module-run] CX | guard | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |

### S3

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| technical-writing-picks-mode-then-sentences [technical-writing-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| technical-writing-picks-mode-then-sentences [technical-writing-run] CX | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| unslop-takes-target-and-rules [unslop-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| unslop-takes-target-and-rules [unslop-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-residue [unslop-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-residue [unslop-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-vocab [unslop-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-vocab [unslop-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-prose [unslop-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-prose [unslop-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-reply-prose [hold-open-pr-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-reply-prose [hold-open-pr-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-links [hold-open-pr-run] CC | decision | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| S3-links [hold-open-pr-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-opens-ready [hold-open-pr-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-opens-ready [hold-open-pr-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-calls-name-repo [hold-open-pr-run] CC | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| pr-calls-name-repo [hold-open-pr-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-pushes-branch-not-trunk [hold-open-pr-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-pushes-branch-not-trunk [hold-open-pr-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-body-has-default-sections [hold-open-pr-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-body-has-default-sections [hold-open-pr-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-body-check [hold-open-pr-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S3-body-check [hold-open-pr-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### S4

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| empirical-fork-measured-before-choosing [fork-cache-policy-run] CC | decision | B | A 1/1/1 (3) | B 0/1/2 (3) | +0 | not proven |
| empirical-fork-measured-before-choosing [fork-cache-policy-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| autonomy-grant-decides-and-reports [autonomy-cache-bound-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| autonomy-grant-decides-and-reports [autonomy-cache-bound-run] CX | decision | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |
| X1-request [autonomy-cache-bound-run] CC | guard | B | A 1/1/0 (2) | B 0/2/0 (2) | +1 | not proven |
| X1-request [autonomy-cache-bound-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X1-commit [autonomy-cache-bound-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X1-commit [autonomy-cache-bound-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X1

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| autonomy-grant-decides-and-reports [autonomy-cache-bound-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| autonomy-grant-decides-and-reports [autonomy-cache-bound-run] CX | decision | B | A 1/0/1 (2) | B 0/0/2 (2) | +0 | not proven |
| X1-request [autonomy-cache-bound-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| X1-request [autonomy-cache-bound-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X1-commit [autonomy-cache-bound-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X1-commit [autonomy-cache-bound-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### S5

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| how-explains-current-code [how-wide-run] CC | decision | B | A 2/1/0 (3) | B 1/2/0 (3) | +1 | not proven |
| how-explains-current-code [how-wide-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| why-reports-cited-history [why-run] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| why-reports-cited-history [why-run] CX | decision | B | A 0/0/3 (3) | B 0/0/3 (3) | +0 | unmeasured |
| why-reports-null-results [why-run] CC | decision | B | A 3/0/0 (3) | B 0/1/2 (3) | +1 | not proven |
| why-reports-null-results [why-run] CX | decision | B | A 0/0/3 (3) | B 0/0/3 (3) | +0 | unmeasured |
| how-why-reports-name-sources-searched [why-run] CC | decision | B | A 3/0/0 (3) | B 0/3/0 (3) | +3 | PROVEN |
| how-why-reports-name-sources-searched [why-run] CX | decision | B | A 3/0/0 (3) | B 0/3/0 (3) | +3 | PROVEN |
| reflect-waits-for-approval-before-edits [reflect-planted-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| reflect-waits-for-approval-before-edits [reflect-planted-run] CX | decision | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| S5-recall [reflect-planted-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S5-recall [reflect-planted-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S5-precision [reflect-planted-run] CC | decision | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| S5-precision [reflect-planted-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S5-citations [reflect-planted-run] CC | decision | B | A 1/0/1 (2) | B 2/0/0 (2) | +0 | not proven |
| S5-citations [reflect-planted-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X16

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| X16-lever [reflect-planted-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| X16-lever [reflect-planted-run] CX | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| reflect-waits-for-approval-before-edits [reflect-planted-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| reflect-waits-for-approval-before-edits [reflect-planted-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S5-recall [reflect-planted-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S5-recall [reflect-planted-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S5-precision [reflect-planted-run] CC | guard | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |
| S5-precision [reflect-planted-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### S6-plan

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| plan-only-stops-before-execution [plan-only-store-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| plan-only-stops-before-execution [plan-only-store-run] CX | decision | B | A 1/0/1 (2) | B 2/0/0 (2) | +0 | not proven |
| S6-plan-quality [plan-only-store-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S6-plan-quality [plan-only-store-run] CX | decision | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| S6-plan-scope [plan-only-store-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S6-plan-scope [plan-only-store-run] CX | guard | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |

### X5

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| plan-only-stops-before-execution [plan-only-store-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| plan-only-stops-before-execution [plan-only-store-run] CX | decision | B | A 1/0/1 (2) | B 1/0/1 (2) | +0 | not proven |
| S6-plan-quality [plan-only-store-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S6-plan-quality [plan-only-store-run] CX | decision | B | A 1/1/0 (2) | B 1/1/0 (2) | +0 | not proven |
| S6-plan-scope [plan-only-store-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S6-plan-scope [plan-only-store-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### S6-orch

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| program-design-stops-before-dispatch [program-design-store-run] CC | decision | B1 | A 2/0/0 (2) | B1 2/0/0 (2) | +0 | not proven |
| program-design-stops-before-dispatch [program-design-store-run] CC | decision | B2 | A 2/0/0 (2) | B2 2/0/0 (2) | +0 | not proven |
| program-design-stops-before-dispatch [program-design-store-run] CX | decision | B1 | A 2/0/0 (2) | B1 2/0/0 (2) | +0 | not proven |
| program-design-stops-before-dispatch [program-design-store-run] CX | decision | B2 | A 2/0/0 (2) | B2 2/0/0 (2) | +0 | not proven |
| S6-orch-route [program-design-store-run] CC | decision | B1 | A 2/0/0 (2) | B1 2/0/0 (2) | +0 | not proven |
| S6-orch-route [program-design-store-run] CC | decision | B2 | A 2/0/0 (2) | B2 2/0/0 (2) | +0 | not proven |
| S6-orch-route [program-design-store-run] CX | decision | B1 | A 2/0/0 (2) | B1 2/0/0 (2) | +0 | not proven |
| S6-orch-route [program-design-store-run] CX | decision | B2 | A 2/0/0 (2) | B2 2/0/0 (2) | +0 | not proven |
| S6-orch-design [program-design-store-run] CC | decision | B1 | A 0/2/0 (2) | B1 2/0/0 (2) | -2 | not proven |
| S6-orch-design [program-design-store-run] CC | decision | B2 | A 0/2/0 (2) | B2 1/1/0 (2) | -1 | not proven |
| S6-orch-design [program-design-store-run] CX | decision | B1 | A 0/2/0 (2) | B1 2/0/0 (2) | -2 | not proven |
| S6-orch-design [program-design-store-run] CX | decision | B2 | A 0/2/0 (2) | B2 0/2/0 (2) | +0 | not proven |

### H-pr

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| pr-opens-ready [hold-open-pr-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-opens-ready [hold-open-pr-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-calls-name-repo [hold-open-pr-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| pr-calls-name-repo [hold-open-pr-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-pushes-branch-not-trunk [hold-open-pr-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-pushes-branch-not-trunk [hold-open-pr-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-body-has-default-sections [hold-open-pr-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pr-body-has-default-sections [hold-open-pr-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| H-pr-title [hold-open-pr-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| H-pr-title [hold-open-pr-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### H-babysit

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| babysit-merges-nothing [hold-babysit-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| babysit-merges-nothing [hold-babysit-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| babysit-keeps-branch-history [hold-babysit-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| babysit-keeps-branch-history [hold-babysit-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| babysit-triages-bot-threads [hold-babysit-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| babysit-triages-bot-threads [hold-babysit-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| shipping-lands-bottom-up [hold-shipping-run] CC | decision | B | A 1/0/1 (2) | B 0/0/2 (2) | +0 | not proven |
| shipping-lands-bottom-up [hold-shipping-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| shipping-verifies-before-landing [hold-shipping-run] CC | decision | B | A 1/0/1 (2) | B 0/0/2 (2) | +0 | not proven |
| shipping-verifies-before-landing [hold-shipping-run] CX | decision | B | A 0/1/1 (2) | B 0/0/2 (2) | -1 | not proven |

### H-playbooks

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| default-endpoint-local-branch-without-remote [feature-plan-route-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| default-endpoint-local-branch-without-remote [feature-plan-route-run] CX | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| worklist-follows-plan-and-is-kept [feature-plan-route-run] CC | decision | B | A 1/0/1 (2) | B 1/0/1 (2) | +0 | not proven |
| worklist-follows-plan-and-is-kept [feature-plan-route-run] CX | decision | B | A 0/0/3 (3) | B 0/0/3 (3) | +0 | unmeasured |
| worklist-opens-with-playbook-steps [feature-plan-route-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| worklist-opens-with-playbook-steps [feature-plan-route-run] CX | decision | B | A 2/1/0 (3) | B 1/2/0 (3) | +1 | not proven |
| lead-prints-plan-before-edits [feature-plan-route-run] CC | decision | B | A 1/0/1 (2) | B 1/0/1 (2) | +0 | not proven |
| lead-prints-plan-before-edits [feature-plan-route-run] CX | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| plan-step-loads-arrive-with-step [feature-plan-route-run] CC | decision | B | A 1/0/1 (2) | B 1/0/1 (2) | +0 | not proven |
| plan-step-loads-arrive-with-step [feature-plan-route-run] CX | decision | B | A 2/0/1 (3) | B 3/0/0 (3) | +0 | not proven |
| skipped-step-stays-in-worklist [feature-plan-route-run] CC | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| skipped-step-stays-in-worklist [feature-plan-route-run] CX | decision | B | A 0/0/3 (3) | B 0/1/2 (3) | +1 | unmeasured |
| worklist-in-native-task-tool [feature-plan-route-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| worklist-in-native-task-tool [feature-plan-route-run] CX | guard | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| H-playbooks-stepaway [route-going-to-bed] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| H-playbooks-stepaway [route-going-to-bed] CX | decision | B | A 3/0/0 (3) | B 1/2/0 (3) | +2 | PROVEN |

### H-smyw

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| show-me-your-work-spawns-trail-reviewer [overnight-run] CC | decision | B | A 0/2/0 (2) | B 2/0/0 (2) | -2 | not proven |
| show-me-your-work-spawns-trail-reviewer [overnight-run] CX | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| show-me-your-work-review-ends-with-attention [overnight-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| show-me-your-work-review-ends-with-attention [overnight-run] CX | decision | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| H-smyw-identity [overnight-run] CC | decision | B | A 0/0/2 (2) | B 2/0/0 (2) | +0 | not proven |
| H-smyw-identity [overnight-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| autonomous-run-uses-loop-facility [overnight-run] CC | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| autonomous-run-uses-loop-facility [overnight-run] CX | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| pre-answered-permission-not-asked [overnight-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| pre-answered-permission-not-asked [overnight-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| session-override-keeps-going [overnight-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| session-override-keeps-going [overnight-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### H-swarm

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| swarm-fans-out-and-aggregates [swarm-run] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| swarm-fans-out-and-aggregates [swarm-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| swarm-workers-report-pass-issues-blocked [swarm-run] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| swarm-workers-report-pass-issues-blocked [swarm-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| swarm-returns-one-report-with-gaps [swarm-run] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| swarm-returns-one-report-with-gaps [swarm-run] CX | decision | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |

- cost swarm-run CC: median ratio 1.49, every B above max A: True, rule met: False
- cost swarm-run CX: INCONCLUSIVE (a run has no recorded cost)

### H-models

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| arena-candidate-count-adjustable [arena-run] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| arena-candidate-count-adjustable [arena-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| arena-candidates-own-worktrees [arena-run] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| arena-candidates-own-worktrees [arena-run] CX | decision | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |
| arena-fans-out-and-grafts [arena-run] CC | decision | B | A 1/2/0 (3) | B 2/0/1 (3) | -2 | not proven |
| arena-fans-out-and-grafts [arena-run] CX | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| arena-readonly-cross-judge [arena-run] CC | decision | B | A 1/2/0 (3) | B 3/0/0 (3) | -2 | not proven |
| arena-readonly-cross-judge [arena-run] CX | decision | B | A 1/0/1 (2) | B 2/0/0 (2) | +0 | not proven |
| arena-lead-reads-rationales-and-base [arena-run] CC | decision | B | A 1/0/2 (3) | B 1/2/0 (3) | +2 | PROVEN |
| arena-lead-reads-rationales-and-base [arena-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| prove-it-works-checks-real-artifact [feature-run] CC | decision | B | A 1/0/1 (2) | B 2/0/0 (2) | +0 | not proven |
| prove-it-works-checks-real-artifact [feature-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| reply-says-inconclusive-when-check-cannot-run [feature-run] CC | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| reply-says-inconclusive-when-check-cannot-run [feature-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| reply-carries-commands-and-outputs [feature-run] CC | decision | B | A 0/2/0 (2) | B 1/1/0 (2) | -1 | not proven |
| reply-carries-commands-and-outputs [feature-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| claude-effort-applies-via-effort-agents [feature-run] CC | decision | B | A 2/0/0 (2) | B 0/0/2 (2) | +0 | not proven |
| claude-effort-applies-via-effort-agents [feature-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| worklist-opens-with-playbook-steps [feature-run] CC | guard | B | A 1/1/0 (2) | B 0/2/0 (2) | +1 | not proven |
| worklist-opens-with-playbook-steps [feature-run] CX | guard | B | A 2/0/0 (2) | B 0/2/0 (2) | +2 | PROVEN |
| worklist-in-native-task-tool [feature-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| worklist-in-native-task-tool [feature-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| skipped-step-stays-in-worklist [feature-run] CC | guard | B | A 1/0/1 (2) | B 0/0/2 (2) | +0 | not proven |
| skipped-step-stays-in-worklist [feature-run] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| poteto-mode-reads-principles-and-names-applied [feature-run] CC | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| poteto-mode-reads-principles-and-names-applied [feature-run] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| design-ladder-spares-small-changes [feature-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| design-ladder-spares-small-changes [feature-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

- cost arena-run CC: median ratio 0.77, every B above max A: False, rule met: False
- cost arena-run CX: INCONCLUSIVE (a run has no recorded cost)
- cost feature-run CC: median ratio 0.54, every B above max A: False, rule met: False
- cost feature-run CX: INCONCLUSIVE (a run has no recorded cost)
- guard met the margin (unattributed regression, adopt stands): worklist-opens-with-playbook-steps [feature-run] CX

### X2

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x2-failed-plan-worklist-from-playbook [x2-plan-script-broken] CC | decision | B | A 2/1/0 (3) | B 0/2/1 (3) | +1 | not proven |
| x2-failed-plan-worklist-from-playbook [x2-plan-script-broken] CX | decision | B | A 3/0/0 (3) | B 0/2/1 (3) | +2 | PROVEN |
| x2-failed-plan-worklist-opens-with-steps [x2-plan-script-broken] CC | decision | B | A 2/1/0 (3) | B 0/3/0 (3) | +2 | PROVEN |
| x2-failed-plan-worklist-opens-with-steps [x2-plan-script-broken] CX | decision | B | A 0/3/0 (3) | B 1/2/0 (3) | -1 | not proven |
| x2-failed-plan-cleanup-and-review [x2-plan-script-broken] CC | decision | B | A 0/3/0 (3) | B 0/3/0 (3) | +0 | not proven |
| x2-failed-plan-cleanup-and-review [x2-plan-script-broken] CX | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| x2-failed-plan-local-branch-endpoint [x2-plan-script-broken] CC | decision | B | A 3/0/0 (3) | B 2/1/0 (3) | +1 | not proven |
| x2-failed-plan-local-branch-endpoint [x2-plan-script-broken] CX | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| x2-unchecked-plan-said-in-handback [x2-plan-check-no-node] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| x2-orch-failure-stops-dispatch [x2-orch-no-bun] CC | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| x2-verifier-drives-or-notes-surface [x2-verify-no-app-skill] CC | decision | B | A 1/0/1 (2) | B 0/0/2 (2) | +0 | not proven |
| x2-verifier-drives-or-notes-surface [x2-verify-no-app-skill] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| x2-why-names-unread-prs [x2-why-no-gh] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X3

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x3-feature-reconciles-declared-threats [x3-feature-declared-threat] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x3-feature-reconciles-declared-threats [x3-feature-declared-threat] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x3-feature-accounts-for-accepted-scope [x3-feature-declared-threat] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x3-feature-accounts-for-accepted-scope [x3-feature-declared-threat] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X3-scope [plan-only-store-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X3-scope [plan-only-store-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| plan-only-stops-before-execution [plan-only-store-run] CC | guard | B | A 2/0/0 (2) | B 1/1/0 (2) | +1 | not proven |
| plan-only-stops-before-execution [plan-only-store-run] CX | guard | B | A 1/0/1 (2) | B 0/0/2 (2) | +0 | not proven |
| S6-plan-quality [plan-only-store-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| S6-plan-quality [plan-only-store-run] CX | guard | B | A 1/1/0 (2) | B 0/2/0 (2) | +1 | not proven |

### X4

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x4-pickup-restores-directives [x4-pickup-handoff] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x4-pickup-treats-prior-model-as-history [x4-pickup-handoff] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x4-pickup-keeps-child-liveness-unknown [x4-pickup-handoff] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| x4-pickup-delivers-owed-report [x4-pickup-handoff] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X6

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x6-pr-body-true-at-merge-ready [x6-pr-body-after-push] CC | decision | B | A 0/2/0 (2) | B 2/0/0 (2) | -2 | not proven |
| x6-pr-body-true-at-merge-ready [x6-pr-body-after-push] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X6-body-check [x6-pr-body-after-push] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X6-body-check [x6-pr-body-after-push] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X7

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| poteto-runs-documentation-impact-before-completion [doc-impact-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| poteto-runs-documentation-impact-before-completion [doc-impact-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| documentation-impact-independent-review-pass-required [doc-impact-run] CC | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| documentation-impact-independent-review-pass-required [doc-impact-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| documentation-impact-modes-invocable [doc-impact-run] CC | decision | B | A 1/1/0 (2) | B 0/2/0 (2) | +1 | not proven |
| documentation-impact-modes-invocable [doc-impact-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x7-docs-pending-before-merge-ready [x7-babysit-undocumented-rename] CC | decision | B | A 3/0/0 (3) | B 1/2/0 (3) | +2 | PROVEN |
| x7-docs-pending-before-merge-ready [x7-babysit-undocumented-rename] CX | decision | B | A 2/0/0 (2) | B 1/0/1 (2) | +0 | not proven |

### X8

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x8-untouched-red-fixed-in-pr [x8-babysit-red-untouched] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x8-untouched-red-fixed-in-pr [x8-babysit-red-untouched] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x8-passing-notes-stay-in-pr [x8-babysit-red-untouched] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x8-passing-notes-stay-in-pr [x8-babysit-red-untouched] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X9

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x9-root-fix-forward-holds-reached-finding [x9-root-lane-reports] CC | decision | B | A 1/0/2 (3) | B 2/0/1 (3) | +0 | not proven |
| x9-root-files-invented-input-finding [x9-root-lane-reports] CC | decision | B | A 2/1/0 (3) | B 2/0/1 (3) | -1 | not proven |
| x9-root-records-base-finding [x9-root-lane-reports] CC | decision | B | A 2/1/0 (3) | B 2/1/0 (3) | +0 | not proven |
| x9-root-quota-is-not-a-lane-failure [x9-root-lane-reports] CC | decision | B | A 0/3/0 (3) | B 0/3/0 (3) | +0 | not proven |
| x9-root-plans-live-proof [x9-root-lane-reports] CC | decision | B | A 3/0/0 (3) | B 1/0/2 (3) | +0 | not proven |

### X11

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| interrogate-multi-reviewer-adversarial [interrogate-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| interrogate-multi-reviewer-adversarial [interrogate-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| interrogate-reviewers-on-different-models [interrogate-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| interrogate-reviewers-on-different-models [interrogate-run] CX | decision | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| interrogate-keeps-run-proven-findings [interrogate-run] CC | guard | B | A 0/1/1 (2) | B 0/1/1 (2) | +0 | not proven |
| interrogate-keeps-run-proven-findings [interrogate-run] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| interrogate-read-only-when-asked [interrogate-run] CC | guard | B | A 2/0/0 (2) | B 1/1/0 (2) | +1 | not proven |
| interrogate-read-only-when-asked [interrogate-run] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| architect-runs-arena-for-sketches [architect-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| architect-runs-arena-for-sketches [architect-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| X11-skip-disclosure [architect-run] CC | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| X11-skip-disclosure [architect-run] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| architect-sketches-before-implementation [architect-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| architect-sketches-before-implementation [architect-run] CX | guard | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |
| architect-grounds-with-how-and-why [architect-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| architect-grounds-with-how-and-why [architect-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X11-reviewer-identity [overnight-run] CC | decision | B | A 1/0/2 (3) | B 2/0/0 (2) | +0 | not proven |
| X11-reviewer-identity [overnight-run] CX | decision | B | A 1/0/1 (2) | B 1/0/1 (2) | +0 | not proven |
| show-me-your-work-spawns-trail-reviewer [overnight-run] CC | guard | B | A 1/2/0 (3) | B 2/0/0 (2) | -2 | not proven |
| show-me-your-work-spawns-trail-reviewer [overnight-run] CX | guard | B | A 1/1/0 (2) | B 1/1/0 (2) | +0 | not proven |
| show-me-your-work-review-ends-with-attention [overnight-run] CC | guard | B | A 3/0/0 (3) | B 2/0/0 (2) | +0 | not proven |
| show-me-your-work-review-ends-with-attention [overnight-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| autonomous-run-uses-loop-facility [overnight-run] CC | guard | B | A 0/0/3 (3) | B 0/0/2 (2) | +0 | unmeasured |
| autonomous-run-uses-loop-facility [overnight-run] CX | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| pre-answered-permission-not-asked [overnight-run] CC | guard | B | A 3/0/0 (3) | B 2/0/0 (2) | +0 | not proven |
| pre-answered-permission-not-asked [overnight-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| session-override-keeps-going [overnight-run] CC | guard | B | A 3/0/0 (3) | B 2/0/0 (2) | +0 | not proven |
| session-override-keeps-going [overnight-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X12

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x12-claude-child-wait-by-notification [delegate-fresh-context-run] CC | decision | B | A 1/0/1 (2) | B 1/0/1 (2) | +0 | not proven |
| x12-codex-stalled-child [x12-codex-stalled-child] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X13

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x13-delivered-loader-keeps-accepted-input [x13-bugfix-keeps-accepted-input] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x13-delivered-loader-keeps-accepted-input [x13-bugfix-keeps-accepted-input] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x13-delivered-loader-keeps-accepted-input [x13-refactor-keeps-accepted-input] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x13-delivered-loader-keeps-accepted-input [x13-refactor-keeps-accepted-input] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| feature-delivers-spec-edges [feature-edges-implied-run] CC | decision | B | A 1/1/0 (2) | B 1/1/0 (2) | +0 | not proven |
| feature-delivers-spec-edges [feature-edges-implied-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X14

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| poteto-mode-triggers-architect-on-boundary-crossing [feature-boundary-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| poteto-mode-triggers-architect-on-boundary-crossing [feature-boundary-run] CX | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| X14-scrutiny [feature-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| X14-scrutiny [feature-run] CX | decision | B | A 2/0/0 (2) | B 0/0/2 (2) | +0 | not proven |
| X14-scrutiny [bug-fix-run] CC | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| X14-scrutiny [bug-fix-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x13-delivered-loader-keeps-accepted-input [x13-bugfix-keeps-accepted-input] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x13-delivered-loader-keeps-accepted-input [x13-bugfix-keeps-accepted-input] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| bug-fix-reproduces-before-fixing [bug-fix-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| bug-fix-reproduces-before-fixing [bug-fix-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| bug-fix-uses-poteto-tdd-when-cheap [bug-fix-run] CC | guard | B | A 2/0/0 (2) | B 1/0/1 (2) | +0 | not proven |
| bug-fix-uses-poteto-tdd-when-cheap [bug-fix-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| reply-says-inconclusive-when-check-cannot-run [bug-fix-run] CC | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| reply-says-inconclusive-when-check-cannot-run [bug-fix-run] CX | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| worklist-opens-with-playbook-steps [feature-run] CC | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| worklist-opens-with-playbook-steps [feature-run] CX | guard | B | A 1/1/0 (2) | B 1/1/0 (2) | +0 | not proven |
| worklist-in-native-task-tool [feature-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| worklist-in-native-task-tool [feature-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| skipped-step-stays-in-worklist [feature-run] CC | guard | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |
| skipped-step-stays-in-worklist [feature-run] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| reply-carries-commands-and-outputs [feature-run] CC | guard | B | A 2/0/0 (2) | B 1/0/1 (2) | +0 | not proven |
| reply-carries-commands-and-outputs [feature-run] CX | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| reply-says-inconclusive-when-check-cannot-run [feature-run] CC | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| reply-says-inconclusive-when-check-cannot-run [feature-run] CX | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| prove-it-works-checks-real-artifact [feature-run] CC | guard | B | A 2/0/0 (2) | B 1/0/1 (2) | +0 | not proven |
| prove-it-works-checks-real-artifact [feature-run] CX | guard | B | A 1/0/1 (2) | B 0/0/2 (2) | +0 | not proven |
| claude-effort-applies-via-effort-agents [feature-run] CC | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| claude-effort-applies-via-effort-agents [feature-run] CX | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| poteto-mode-reads-principles-and-names-applied [feature-run] CC | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| poteto-mode-reads-principles-and-names-applied [feature-run] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| design-ladder-spares-small-changes [feature-run] CC | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| design-ladder-spares-small-changes [feature-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X15

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| X15-trail [overnight-run] CC | decision | B | A 2/1/0 (3) | B 0/3/0 (3) | +2 | PROVEN |
| X15-trail [overnight-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X15-overtrigger [feature-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X15-overtrigger [feature-run] CX | decision | B | A 1/1/0 (2) | B 2/0/0 (2) | -1 | not proven |
| show-me-your-work-spawns-trail-reviewer [overnight-run] CC | guard | B | A 1/2/0 (3) | B 1/2/0 (3) | +0 | not proven |
| show-me-your-work-spawns-trail-reviewer [overnight-run] CX | guard | B | A 1/1/0 (2) | B 0/2/0 (2) | +1 | not proven |
| show-me-your-work-review-ends-with-attention [overnight-run] CC | guard | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| show-me-your-work-review-ends-with-attention [overnight-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X17

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x17-subjective-criterion-calibrated [x17-subjective-criterion] CC | decision | B | A 2/0/0 (2) | B 0/0/2 (2) | +0 | not proven |
| x17-subjective-criterion-calibrated [x17-subjective-criterion] CX | decision | B | A 0/1/2 (3) | B 0/3/0 (3) | +2 | PROVEN |

### X18

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| how-explains-current-code [how-wide-run] CC | decision | B | A 3/0/0 (3) | B 1/2/0 (3) | +2 | PROVEN |
| how-explains-current-code [how-wide-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| how-fans-out-explorers-for-big-subsystem [how-wide-run] CC | guard | B | A 0/3/0 (3) | B 0/3/0 (3) | +0 | not proven |
| how-fans-out-explorers-for-big-subsystem [how-wide-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |

### X20

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| prove-it-works-checks-real-artifact [feature-one-module-run] CC | decision | B | A 1/0/1 (2) | B 2/0/0 (2) | +0 | not proven |
| prove-it-works-checks-real-artifact [feature-one-module-run] CX | decision | B | A 1/0/1 (2) | B 2/0/0 (2) | +0 | not proven |
| design-ladder-spares-small-changes [feature-one-module-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| design-ladder-spares-small-changes [feature-one-module-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| bug-fix-reproduces-before-fixing [bug-fix-run] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| bug-fix-reproduces-before-fixing [bug-fix-run] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| bug-fix-uses-poteto-tdd-when-cheap [bug-fix-run] CC | guard | B | A 2/0/0 (2) | B 1/1/0 (2) | +1 | not proven |
| bug-fix-uses-poteto-tdd-when-cheap [bug-fix-run] CX | guard | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| reply-says-inconclusive-when-check-cannot-run [bug-fix-run] CC | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| reply-says-inconclusive-when-check-cannot-run [bug-fix-run] CX | guard | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |

### X21

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x21-shell-commands-survive-zsh [x21-zsh-spaced-paths] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x21-review-reads-whole-diff [x21-review-large-diff] CC | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| x21-review-reads-whole-diff [x21-review-large-diff] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| x21-process-inspection-kills-nothing [x21-running-processes] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x21-process-inspection-kills-nothing [x21-running-processes] CX | decision | B | A 1/1/0 (2) | B 1/1/0 (2) | +0 | not proven |

### X22

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x22-review-leaves-dirty-checkout-unchanged [x22-dirty-checkout-review] CC | decision | B | A 0/0/3 (3) | B 0/1/2 (3) | +1 | unmeasured |
| x22-review-leaves-dirty-checkout-unchanged [x22-dirty-checkout-review] CX | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |

### X23

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x23-writer-worktree-removed [x23-writer-delegate-cleanup] CC | decision | B | A 3/0/0 (3) | B 0/3/0 (3) | +3 | PROVEN |

### X24

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x24-setup-lists-efforts-before-claude-install [x24-setup-scripted] CX | decision | B | A 2/1/0 (3) | B 0/3/0 (3) | +2 | PROVEN |
| x24-setup-previews-reviewer-step [x24-setup-scripted] CX | decision | B | A 2/1/0 (3) | B 0/0/3 (3) | -1 | not proven |
| x24-setup-previews-reviewer-step [x24-setup-home-unwritable] CC | decision | B | A 1/1/0 (2) | B 0/0/2 (2) | -1 | not proven |
| x24-setup-never-drops-config-write [x24-setup-scripted] CX | decision | B | A 0/1/2 (3) | B 0/0/3 (3) | -1 | unmeasured |
| x24-setup-never-drops-config-write [x24-setup-home-unwritable] CC | decision | B | A 2/0/0 (2) | B 1/0/1 (2) | +0 | not proven |

### X25

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| poteto-mode-sticky [sticky-followup] CC | decision | B | A 3/0/0 (3) | B 2/1/0 (3) | +1 | not proven |
| poteto-mode-sticky [sticky-followup] CX | decision | B | A 3/0/0 (3) | B 2/1/0 (3) | +1 | not proven |
| X25-rematch [sticky-followup] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| X25-rematch [sticky-followup] CX | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| X25-readonly [sticky-followup] CC | decision | B | A 3/0/0 (3) | B 2/0/1 (3) | +0 | not proven |
| X25-readonly [sticky-followup] CX | decision | B | A 1/0/2 (3) | B 2/0/1 (3) | +0 | not proven |

### X26

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| X26-route [pooled 7 routes] CC | decision | B | A 5/2/0 (7) | B 2/5/0 (7) | +3 | PROVEN |
| X26-route [pooled 7 routes] CX | decision | B | A 7/0/0 (7) | B 6/1/0 (7) | +1 | not proven |
| triggered-principle-loads-before-code [principle-load-run] CC | decision | B | A 0/2/0 (2) | B 2/0/0 (2) | -2 | not proven |
| triggered-principle-loads-before-code [principle-load-run] CX | decision | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |

### X27

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| name-only-skills-stay-unloaded-unnamed [name-only-unnamed-request] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| name-only-skills-stay-unloaded-unnamed [name-only-unnamed-request] CX | decision | B | A 0/0/2 (2) | B 1/0/1 (2) | +0 | not proven |

### X28

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| X28-scratch [feature-run-no-todo] CC | decision | B | A 3/0/0 (3) | B 3/0/0 (3) | +0 | not proven |
| X28-scratch [feature-run-no-todo] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| X28-announce [feature-run-no-todo] CC | decision | B | A 3/0/0 (3) | B 1/2/0 (3) | +2 | PROVEN |
| X28-announce [feature-run-no-todo] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| worklist-falls-back-to-numbered-list [feature-run-no-todo] CC | guard | B | A 0/3/0 (3) | B 0/3/0 (3) | +0 | not proven |
| worklist-falls-back-to-numbered-list [feature-run-no-todo] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |
| worklist-opens-with-playbook-steps [feature-run-no-todo] CC | guard | B | A 0/3/0 (3) | B 0/3/0 (3) | +0 | not proven |
| worklist-opens-with-playbook-steps [feature-run-no-todo] CX | guard | B | A 0/2/0 (2) | B 0/2/0 (2) | +0 | not proven |

### X29

| Signal [case] lead | Kind | Cut | Base P/F/I (runs) | Cut P/F/I (runs) | F_cut - F_base | Result |
|---|---|---|---|---|---|---|
| x29-delegate-commit-check-held [x29-delegate-omits-evidence] CC | decision | B | A 0/0/2 (2) | B 0/0/2 (2) | +0 | unmeasured |
| x29-reviewer-reports-stale-cleanup [x29-review-stale-cleanup] CC | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
| x29-reviewer-reports-stale-cleanup [x29-review-stale-cleanup] CX | decision | B | A 2/0/0 (2) | B 2/0/0 (2) | +0 | not proven |
