# Step-away and program-scale trigger screen, 2026-11-25

Issue #600. Orchestrate is gone, so figure-it-out is the only route for multi-day, step-away, and program-scale work. In the [2026-11-25 live reruns](2026-11-25-sync-0b46ec3-live.md#follow-up-runs-on-the-disputed-cells), Claude Code leads reached it in 1 of 3 runs of `route-going-to-bed` and of `overnight-run`, and one miss opened Refactoring first. This screen compares two rewordings of the poteto-mode entry's trigger against main.

Arm **b** ships. Both candidates beat main by the screens' margin on Claude Code, and neither regressed on either lead.

The counting rule and its scorer were written before the first screen run started. This file reached the branch before any run was counted by arm.

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
- The rule filed before the first run broke a remaining tie by fewer guard failures, then by fewer entry bytes. The first version of this file left out those two tie-breaks.

## Results

Each cell shows how its 3 runs graded after the trace checks below.

| Cell | Lead | base | a | b |
|---|---|---|---|---|
| bed | Claude Code | 2 FAIL, 1 PASS | 3 PASS | 3 PASS |
| bed | Codex | 1 FAIL, 1 PASS, 1 inconclusive | 1 FAIL, 2 PASS | 1 FAIL, 2 PASS |
| overnight | Claude Code | 2 FAIL, 1 PASS | 3 PASS | 3 PASS |
| overnight | Codex | 1 FAIL, 2 inconclusive | 1 PASS, 2 inconclusive | 2 PASS, 1 inconclusive |
| guard | Claude Code | 3 PASS | 3 PASS | 3 PASS |
| guard | Codex | 3 PASS | 3 PASS | 3 PASS |

- **Both candidates beat base.** On Claude Code, base failed 2 of 3 runs in each step-away cell, and each candidate failed none. Three of the four base misses opened another playbook first: `plan.py refactoring` twice on the overnight prompt and `bug-fix` once on the going-to-bed prompt. In the fourth, the fixtures already passed, and the lead stopped without routing.
- **Neither candidate regressed.** No guard run on any arm loaded figure-it-out. In the Codex step-away cells, the arms differ by at most one failure. On Codex `overnight`, base and a each have 2 inconclusive runs, so that pair is unmeasured for a.
- **b ships on the last tie-break.** The two candidates tie on step-away failures (1 each) and guard failures (0 each), so the smaller entry wins: b is 7 bytes shorter than main, and a is the same size.

### Trace checks

A hand read of the trace checked every FAIL and every run the sweeps flagged. Six verdicts became inconclusive, and none became PASS or FAIL.

- The scorer misses a skill read inside a brace glob or a shell loop, such as `cat .agents/skills/{figure-it-out,show-me-your-work}/SKILL.md`. Three Codex FAILs had read figure-it-out that way before the playbook the scorer cited.
- When one tool call or one parallel batch reads figure-it-out together with a playbook or runs `plan.py`, the order inside the batch is not a routing decision. Three Codex runs, one FAIL and two PASSes, became inconclusive this way. The rule for PASSes and ties was added before the counts were unsealed.
- Eight FAILs stand. The four on Claude Code ran `plan.py` for another playbook, or stopped without routing, and never loaded figure-it-out. The four on Codex read a playbook file in an earlier batch than figure-it-out.

The routing oracles graded these runs differently. `in-conversation-run-skips-figure-it-out` failed 9 guard runs, with 3 on base, because they routed through `plan.py` without a playbook read or a worklist. Issue #590 tracks that oracle gap. None of the 9 loaded figure-it-out.

### Run ids

- base, Claude Code: `relay-1bo0em6z`, `relay-c620la4g`, `relay-e0a8d_x2`, `relay-eof6sva8`, `relay-oiv72iyr`, `relay-pn7ze7qg`, `rollup-15bmgpu0`, `rollup-bt3r2eos`, `rollup-djpii9l_`.
- base, Codex: `relay-0spiv3f4`, `relay-3ip3hcnm`, `relay-_vgiwprf`, `relay-ch6bh5ca`, `relay-sakt74qb`, `relay-swxs3_bi`, `rollup-rs3_nodk`, `rollup-vomm3_0l`, `rollup-xqxervn1`.
- a, Claude Code: `relay-3mb4l1bn`, `relay-aa1gdc_o`, `relay-h6nk9hts`, `relay-i3rzoy7m`, `relay-napy_end`, `relay-ncnyuzgi`, `rollup-itxgq8ac`, `rollup-l5bu_z49`, `rollup-x9fujw0b`.
- a, Codex: `relay-07y56r2q`, `relay-__i64l3f`, `relay-f9x_8190`, `relay-j4_s991i`, `relay-sdbalkbt`, `relay-ylaj19an`, `rollup-9ibqs07g`, `rollup-c9rltfwh`, `rollup-pzgcdf22`.
- b, Claude Code: `relay-0trl2698`, `relay-5jawo81s`, `relay-agqstk5g`, `relay-kc4otu78`, `relay-lxg0pcpl`, `relay-wtn56bv6`, `rollup-e7q9yv24`, `rollup-kcjcnf9o`, `rollup-q4at6fd4`.
- b, Codex: `relay-0h4a64kn`, `relay-1njnvl8g`, `relay-7hyjhdwf`, `relay-86_q7w6o`, `relay-j74h_bz6`, `relay-vn9ydvy8`, `rollup-bwyejbpb`, `rollup-cgawn_6t`, `rollup-pab5w8vo`.

## Limits

- Three runs per cell show a large effect on Claude Code, not a rate. The Codex cells cannot separate the arms.
- Hermes and Grok Build did not run.
- The screen ran `overnight-route`, the first turn of `overnight-run`, not the full case, so `overnight-contract-routes-to-figure-it-out` and the decision-log half of the overnight contract did not rerun.
- The gain is on Claude Code only. On Codex, `bed` failed once on every arm, and no candidate changed the Codex step-away miss that #600 reported.
- Four arm a runs on Codex hit their time limit after doing work, and their verdicts stand as graded. No base or b run timed out.
- The arm commits are on `refs/pstack/wip/screen-600/arm-a` and `refs/pstack/wip/screen-600/arm-b`. The run checkout was main plus this PR's `overnight-route` case.
- Other routes that pass through the entry, such as Feature and Refactoring requests with no step-away cue, were not rerun. The new list entry changes no other entry's text. It names Refactoring, Feature, and Autonomous run only to send step-away and program-scale work to figure-it-out ahead of them.
