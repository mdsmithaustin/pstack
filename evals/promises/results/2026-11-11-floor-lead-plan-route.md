# Plan route on a floor lead, 2026-11-11

This is the first model run against the routing added on 2026-11-10. It asks whether a floor lead runs the plan script, loads the skills the plan prints, keeps a worklist, and reaches the default endpoint.

**The routing did not hold on this lead.** Two of three leads never ran the plan script, kept no worklist, and left the change uncommitted. Both gave the unset `PSTACK_SKILLS_ROOT` and the size of the change as the reason. The third set the variable itself, got the lightweight route, loaded `spec-probes` before its first write, and committed on a named branch. It never loaded `principle-prove-it-works` and kept no worklist. No lead in any run opened a worklist.

Three runs cannot show a rate. The counting rule and the labels below were written before the first run.

## What ran

- Harness: Claude Code 2.1.322 with `claude-sonnet-5-5` at effort medium, TODO tools on. One arm, three runs in sequence, none retried or replaced.
- Command: `python3.14 evals/promises/live.py run --harness claude-code --model claude-sonnet-5-5 --effort medium --skills-at 0cabc614 --runs 3 --case feature-plan-route-run --out <dir>`.
- Skills: `0cabc614`, whose skill tree matches trunk `73f6e452`. This branch changes no skill text.
- Case: `feature-plan-route-run`, the `tally` fixture with the `feature-run` turn and no remote.
- Run ids: `tally-4mufg78h`, `tally-v_6uk6dp`, `tally-cwex8hti`, in run order. They took 26, 49, and 29 seconds.

## Counting rule

One run is one observation per promise. The count is runs graded PASS over runs graded PASS or FAIL. INCONCLUSIVE runs are listed beside it and never converted. Each run carries the route its last routed plan printed. A run with no routed plan that changed the project is a FAIL for the plan promise and INCONCLUSIVE for `plan-step-loads-arrive-with-step` and `worklist-follows-plan-and-is-kept`. Every FAIL and INCONCLUSIVE trace was read before it was counted. An oracle error found by reading is fixed with a control test, every run is regraded, and both counts are reported.

Labels: "held" is PASS in every graded run with at least 2 graded. "Did not hold" is FAIL in at least 2 runs. "Mixed" is anything else with at least 2 graded. "Not shown" is fewer than 2 graded runs.

## Results

| Promise | PASS of graded | INCONCLUSIVE | Label |
|---|---|---|---|
| `lead-prints-plan-before-edits` | 1 of 3 | 0 | Did not hold |
| `plan-step-loads-arrive-with-step`, sealed verdicts | 0 of 0 | 3 | Not shown |
| `plan-step-loads-arrive-with-step`, regraded | 0 of 1 | 2 | Not shown |
| `worklist-follows-plan-and-is-kept`, sealed verdicts | 0 of 0 | 3 | Not shown |
| `worklist-follows-plan-and-is-kept`, regraded | 0 of 1 | 2 | Not shown |
| `default-endpoint-local-branch-without-remote` | 1 of 3 | 0 | Did not hold |
| `worklist-opens-with-playbook-steps` | 0 of 3 | 0 | Did not hold |
| `worklist-in-native-task-tool` | 0 of 3 | 0 | Did not hold |

One run reached a route, and it was lightweight. On that run alone the plan and endpoint promises passed. `worklist-opens-with-playbook-steps` and `worklist-in-native-task-tool` failed. `plan-step-loads-arrive-with-step` and `worklist-follows-plan-and-is-kept` failed on the regrade only, and their sealed verdicts are INCONCLUSIVE.

**The two regraded rows correct a grader gap.** In `tally-v_6uk6dp` the sealed verdicts for the step-load and worklist promises read `the installed skills hold no routes.json`. The grader copied only the mode entry and the playbooks into its skills input, so the oracles could not derive the plan. The commit after this run adds `routes.json` to that copy, with a control test. The regraded rows come from calling `oracles.check` directly on the three saved traces and projects with the fixed input. That call is outside the sealed grader, so `receipts.json` keeps the sealed INCONCLUSIVE verdicts. No run after the fix has shown the two oracles grading inside the sealed grader.

## What each lead did

- **`tally-4mufg78h` and `tally-cwex8hti`.** Each lead's first command printed `PSTACK_SKILLS_ROOT` and found it unset. Neither called the Skill tool, read a skill file, or ran the plan script. Each edited `tally/__main__.py`, compared the text output with the committed version, and replied without a commit. The replies say "I skipped the poteto-mode plan script and worklist because `PSTACK_SKILLS_ROOT` was unset and the change was one small edit" and "because `PSTACK_SKILLS_ROOT` isn't set here and this is a two-line change".
- **`tally-v_6uk6dp`.** The lead listed `.claude/skills`, ran `export PSTACK_SKILLS_ROOT=$PWD/.claude/skills`, and printed the pending plan. It read `routes.md`, recorded five low facts with evidence, and got the lightweight route. It created the branch `json-flag`, loaded `spec-probes` with the Skill tool, wrote the change, ran the preserve gate, committed, and named the branch and `git diff main..json-flag` in the reply. It never loaded `pstack-harness` or `principle-prove-it-works`, and created no worklist in any carrier. Its reply lists the gate skills it skipped and says it did no independent review.

## Why two leads skipped the plan script

The skips are not a runner artifact. They are lead non-compliance with a fallback the entry states, and an instruction gap made the skip easy.

- **A real install leaves the variable unset too.** No installer or setup step writes `PSTACK_SKILLS_ROOT`. The only setter in the skill tree is the block in `skills/pstack-harness/references/portable-paths.md` (lines 11 to 18), which derives it from the path of the loaded `pstack-harness/SKILL.md`. The Claude Code adapter builds a fixed environment (`harnesses/claude_code.py`, line 337) without the variable, as a user's shell would be. `test_claude_code.py` already runs that resolver block inside the run's sandbox policy and expects the host result.
- **The entry prints the command before it names the resolver.** `skills/poteto-mode/SKILL.md` line 23 gives the plan command with `${PSTACK_SKILLS_ROOT:?}`. The entry names `pstack-harness` only afterwards, on line 28, as the way to choose the worklist carrier. The row that sends a lead to the resolver sits inside `pstack-harness/SKILL.md` (line 27). A lead that follows the entry in order meets the unset variable before any sentence tells it where the value comes from. The skill listing did show the `pstack-harness` description, which says it covers "how to locate installed skills", in all three runs.
- **The entry's fallback was reachable and was not followed.** Line 28 says that if the script cannot run, the lead copies the playbook's opening prose and steps as the worklist items and uses the standard route. That sentence was in context in every run. The two leads opened no worklist and read no playbook. Neither tried the script, so neither found out whether it could run. Both also gave the size of the change as a reason, which the entry rules out: a skip reason "says why the outcome does not apply, never what the route costs".
- **The third lead shows the step is passable.** It guessed the root from the directory listing. It did not use the documented resolver either.

Under the counting rule these two runs stay FAIL for the plan promise. No run was excluded or replaced.

## What this says about the open issues

- **#421, rescoped.** Printing loads in the plan does not reach a lead that never prints the plan, which was 2 of 3 here. In the one run that printed it, the lead loaded the pre-code skill and skipped the proof-step skill. One run is not evidence either way on whether printed loads are followed. The issue's comparison of inlined rules against loaded ones is still open.
- **#439, still open.** This run did not exercise `feature-boundary-run`. Since the panels now load only on the intensive route, that case's result depends first on whether the lead prints a plan at all.
- **#484, still open.** The citation rule rides on Feature step 4 and `spec-probes`. One of three leads loaded `spec-probes`. No run wrote a test, so there was nothing to cite.
- **#474, partly answered.** The step-load verdict now reports entry rereads, per-load mechanism and order, step text calls, and unlisted skill loads in `verdict.json`. It reported 0 entry rereads in the one run it graded. The narrow-role delegate read and the Codex skill-text share are not covered.

## Proposed follow-ups

This branch changes no skill text. These are proposals for separate changes, each needing its own run.

1. Give the entry a plan command that needs no prior setup, or put the resolver step before it. Then rerun this case.
2. Make the missing worklist visible to the lead at the point it skips. The 2026-10 risk named in the suite alignment audit, that a printed plan replaces the worklist, matches the one run that printed a plan: it treated the plan as its checklist and opened no carrier.
3. Run this case on Codex, where the same variable is unset and the load mechanism differs.

## Limits

- One harness, one model, one effort, one small feature, three runs.
- The step-load and worklist oracles have one graded run, read outside the sealed grader.
- In `tally-v_6uk6dp` the lead wrote the source through a Python heredoc that opens a path held in a variable. The edit detector missed it, so the trace's first recorded project write is the later README append. By hand the order is the same: the routed plan returned at event 13, `spec-probes` at 17, and the source write ran at 18.
- The oracles do not grade whether the recorded facts are true, the gates, or independent scrutiny. The third lead's reply says it ran neither the cleanup gates nor a review.
- The traces are kept outside the repository, under the maintainer's local audit folder for this date.

## Oracle changes after this run

Review of this change altered six verdict rules after the run. None came from reading these traces.

- A plan call with no recorded failure and no route line, which returned before the first project write, grades INCONCLUSIVE for the plan promise.
- A call that prints the plan more than once and shows only a pending route in its output head grades INCONCLUSIVE for the plan promise.
- A plan script run by a relative path is a plan call.
- A routed plan counts when a later command in the same shell call fails. The route line must sit in the output block for the case's playbook.
- Worklist state changes count from the first snapshot whose items match the plan's.
- The reply must name the delivering branch as a word of its own.

The three runs were not regraded. A read of the saved traces shows that no run has a changed shape. `tally-4mufg78h` and `tally-cwex8hti` hold no plan call and no worklist snapshot. In `tally-v_6uk6dp` the routed plan ran alone by its full path, its recorded output head opens with the `playbook: feature` line and the lightweight route, and the reply names `json-flag` in backticks. No trace holds a worklist snapshot. The traces are outside the repository, so a reader cannot check this from it.
