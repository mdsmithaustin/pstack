# Plan route on a floor lead, second run, 2026-11-11

This is the second run of `feature-plan-route-run`. The [first run](2026-11-11-floor-lead-plan-route.md) found that two of three leads never ran the plan script, and both named the unset `PSTACK_SKILLS_ROOT`. This run tests one change. The entry's plan command now reads `<this skill's base directory>/scripts/plan.py` and names no environment variable.

**All three leads printed a routed plan before their first edit, against one of three in the first run.** No lead printed or probed `PSTACK_SKILLS_ROOT`. All three committed on a named branch, against one of three. What follows the plan did not hold. Two of three leads loaded no skill the plan printed, and two of three opened no worklist. The third opened a worklist with one item, the opening item, and none of the plan's three outcome items.

Three runs cannot show a rate. The counting rule and the labels are the first record's, unchanged, and this run's command was written down before it started.

## What ran

- Harness: Claude Code 2.1.322 with `claude-sonnet-5-5` at effort medium, TODO tools on. One arm, three runs in sequence, none retried or replaced. No run errored.
- Command: `python3.14 evals/promises/live.py run --harness claude-code --model claude-sonnet-5-5 --effort medium --skills-at 404ddca10f4d64c8bd9111935dff724382e5f204 --runs 3 --case feature-plan-route-run --out <dir>`, run from a checkout of `404ddca1`.
- Case: `feature-plan-route-run`, with the same case digest as the first run, `750da31d`.
- Run ids: `tally-mxywu96_`, `tally-sivkd6dc`, `tally-hfugohri`, in run order. They took 41, 34, and 47 seconds, between 19:55 and 19:57 UTC.

Two conditions differ from the first run.

- **Skills.** The first run used `0cabc614`. This run used `404ddca1`. The skill trees differ by one line, the plan command in `skills/poteto-mode/SKILL.md` (`git diff --stat 0cabc614 404ddca1 -- skills/`).
- **Grader.** The first run's receipts carried grader digest `012fcbea`. This run's receipts carry `cd329529`. The grader gained the `routes.json` input and the six verdict rules that the first record lists under "Oracle changes after this run". The first run was not regraded under the newer grader. The first record says that no saved trace has a shape those rules change.

The harness version, model, effort, case, fixture, and turn are the same.

## Counting rule

The [first record's counting rule](2026-11-11-floor-lead-plan-route.md#counting-rule) and its labels apply unchanged. Every trace was read in full before any count, PASS traces included. Each sealed verdict matches its trace, so no run was regraded.

## Results

Each cell is PASS of graded, then the INCONCLUSIVE count.

| Promise | First run | Second run | Second run label |
|---|---|---|---|
| `lead-prints-plan-before-edits` | 1 of 3, 0 | 3 of 3, 0 | Held |
| `plan-step-loads-arrive-with-step` | sealed 0 of 0, 3. Regraded 0 of 1, 2 | 1 of 3, 0 | Did not hold |
| `worklist-follows-plan-and-is-kept` | sealed 0 of 0, 3. Regraded 0 of 1, 2 | 0 of 2, 1 | Did not hold |
| `default-endpoint-local-branch-without-remote` | 1 of 3, 0 | 3 of 3, 0 | Held |
| `worklist-opens-with-playbook-steps` | 0 of 3, 0 | 0 of 3, 0 | Did not hold |
| `worklist-in-native-task-tool` | 0 of 3, 0 | 1 of 3, 0 | Did not hold |

Every run got the lightweight route. The second run's verdicts are all sealed verdicts. The step-load and worklist oracles graded inside the sealed grader for the first time, which the first record listed as not yet shown.

The one INCONCLUSIVE is `tally-hfugohri` on `worklist-follows-plan-and-is-kept`. The oracle found a kept worklist whose item names do not match the plan's and left the decision to a reader. The worklist holds one item, `feature playbook opening`. That is the plan's opening item, which the oracle does not match, and none of the three outcome items exists. The verdict stays INCONCLUSIVE under the counting rule.

## What each lead did

No lead named `PSTACK_SKILLS_ROOT` in any command or message. Each filled the placeholder with the project's own install path, `.claude/skills/poteto-mode`.

- **`tally-mxywu96_`.** The first command listed the files and ran `python3 .claude/skills/poteto-mode/scripts/plan.py feature --harness claude-code`, which printed the pending plan. The lead read the source and `routes.md`, then reran the script with five low facts and got the lightweight route. It created the branch `add-json-flag`, wrote the change, compared text output with the start commit, and committed. It called no Skill tool and opened no worklist. The reply says it did not run `deslop` or `documentation-impact` and that independent review is pending.
- **`tally-sivkd6dc`.** The lead listed `.claude/skills`, read the source, then ran `cd .claude/skills/poteto-mode && python3 scripts/plan.py feature --harness claude-code`. It reran the script by its path from the project root with five low facts and got the lightweight route. It used the branch `json-flag`, wrote the change, compared text output, appended one README line, and committed. It called no Skill tool and opened no worklist. The reply says no independent review happened.
- **`tally-hfugohri`.** The lead listed the mode's `references` folder, read the source and `routes.md`, and ran the script once, with five low facts, by the same relative path. It then loaded `pstack-harness`, `spec-probes`, and `principle-prove-it-works` with the Skill tool, fetched the task tools, and created one task, `feature playbook opening`. It wrote the change on `add-json-flag`, compared text output on six inputs, committed, and closed the task. The reply says it ran neither the cleanup gates nor independent scrutiny.

**The plan's own `${PSTACK_SKILLS_ROOT}` lines (#506).** Every plan printed the playbook path and the preserve gate with the variable. No lead opened `playbooks/feature.md`, by that path or any other, and no lead printed a step's text. All three ran the preserve gate before the commit by replacing the variable with a relative path: `.claude/skills/poteto-mode/scripts/../../pstack-harness/scripts/preserve.py`, `.claude/skills/poteto-mode/../pstack-harness/scripts/preserve.py`, and `.claude/skills/pstack-harness/scripts/preserve.py`. The gate reported nothing to preserve, since the fixture has no tests. No lead ran a gate command as printed, so no run shows the printed command failing.

## What this run shows and does not show

- **The plan promise moved from 1 of 3 to 3 of 3.** In the first run each lead's first command printed the variable. In this run no lead looked for it, and each ran the script within its first three commands. The skills differ by that one line. Three runs per side cannot separate the change from run-to-run variation, and the grader also changed between the runs.
- **The endpoint promise moved with it, from 1 of 3 to 3 of 3.** In both runs, every lead that got a route committed on a named branch and every lead that got none left the change uncommitted.
- **Printing the plan did not carry the rest.** Of four leads that printed a routed plan across both runs, one loaded every printed step load, one loaded `spec-probes` only, and two loaded none. None kept a worklist of the plan's items. The plan's first sentence tells the lead to create the worklist from its items, and three of the four created nothing.
- **Not shown.** Any rate. Any other harness, model, or effort. Whether a lead that tries a printed `${PSTACK_SKILLS_ROOT}` command as written recovers. Whether the recorded risk facts are true, and whether the gates and independent scrutiny ran, since the oracles do not grade them.

## Follow-ups

- **#501, the missing worklist.** This run adds three observations: no worklist in two runs, and an opening item alone in the third. The plan was in context in all three.
- **#506, the variable in the plan's output.** Three leads worked around it for the preserve gate. None opened the playbook the plan's first line points to.
- Step loads after a printed plan held in one of three runs here. No issue tracks that on its own. The first record files the question of whether leads follow printed loads under #421.

## Limits

- One harness, one model, one effort, one small feature, three runs.
- Each lead wrote the source through a Python heredoc that opens a path held in a variable, and the edit detector missed it, as in the first run. The verdicts name a later write as the first project write (seq 19, 24, and 30). By hand the source writes are at seq 17, 18, and 26, each after the routed plan at seq 5, 8, and 5. In `tally-hfugohri` both step loads returned by seq 12. No verdict changes.
- In `tally-mxywu96_` the step-load failure text names a scratch folder as the first code write. The run loaded neither skill, so the FAIL stands.
- `worklist-opens-with-playbook-steps` matches the playbook's nine steps. The lightweight plan prints three outcome items. No run here had a worklist that either reading would pass.
- The traces are kept outside the repository, under the maintainer's local audit folder for this date.
