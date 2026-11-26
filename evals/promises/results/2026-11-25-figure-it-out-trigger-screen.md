# Step-away and program-scale trigger screen, 2026-11-25

Issue #600. Orchestrate is gone, so figure-it-out is the only route for multi-day, step-away, and program-scale work. In the [2026-11-25 live reruns](2026-11-25-sync-0b46ec3-live.md#follow-up-runs-on-the-disputed-cells), Claude Code leads reached it in 1 of 3 runs of `route-going-to-bed` and of `overnight-run`, and one miss opened Refactoring first. This screen compares two rewordings of the poteto-mode entry's trigger against main.

The counting rule below reached the branch before the first screen run finished.

## Arms

Each arm differs from main only in `skills/poteto-mode/SKILL.md`. Neither adds bytes to the entry, because many routes have no byte slack.

- **base.** Main at `72c9676d`. The trigger is one paragraph after the worklist rules: "For a large or cross-cutting effort (...), or work the user steps away from to trust later, call the Skill tool with `figure-it-out` even when a narrower playbook like Feature fits."
- **a.** `58319371`. A check before matching, at the top of the Playbooks section: "Before you match a playbook, call the Skill tool with `figure-it-out` in these cases, even when Refactoring, Feature, or Autonomous run fits:", then one line for a user who steps away ("going to bed", "stepping away", "overnight") and one for a migration across many call sites, a multi-day program, or an ambitious multi-part change.
- **b.** `1bf533e4`. The same two cases as the first entry of the playbook list, `**Step-away or program-scale work.**`, naming the same rivals.

In both candidates the old paragraph shrinks to its last rule, "Call the Skill tool with `figure-it-out` whenever no bundled playbook fits."

## Cells and leads

| Cell | Case | Passes when |
|---|---|---|
| bed | `route-going-to-bed` | the lead's first routing event is figure-it-out |
| overnight | `overnight-route` | the lead's first routing event is figure-it-out |
| guard | `route-autonomous-run` | the lead's first routing event is not figure-it-out |

`overnight-route` is the first turn of `overnight-run` with a 600-second limit (720 on Codex), so its routing can run three times per arm without the 40-minute overnight timeout.

Leads: Claude Code with `claude-sonnet-5-5` and Codex with `gpt-6.2-sol`, both at effort high, with `--workspace-models`. Each arm runs 3 times per cell per lead, 54 runs in all.

## Counting rule

A routing event is a playbook file read, a `plan.py <stem>` call that returned without error, a returned load of `figure-it-out/SKILL.md`, or an opening worklist identified as a playbook. The routing oracles do not credit `plan.py` calls (#590), so the screen scores the first routing event from each trace instead and reports the oracle verdicts beside it.

- A step-away run fails when its first routing event is not figure-it-out, when it finished with no routing event, or when it was killed after 3 or more tool calls with none. A run killed before 3 tool calls with no routing event is inconclusive.
- A guard run fails when its first routing event is figure-it-out, and is inconclusive with no routing event.
- The adjudicator checks every FAIL's cited event against the trace before counting. A FAIL the trace does not support becomes inconclusive. Inconclusive runs never count.
- A candidate beats base when, on one lead and one step-away cell, it fails at least 2 fewer of 3 runs than base. It regresses when, on any lead and any cell, the guard included, it fails at least 2 more.
- A candidate ships only when it beats base and regresses nowhere. When both qualify, the one with fewer step-away failures ships. With no winner, the entry keeps its current text.

## Results

The screen is running. Counts, run ids, and the decision follow here.
