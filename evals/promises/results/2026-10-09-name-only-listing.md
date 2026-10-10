# Name-only skill listing live runs, 2026-10-09

**Status: ISSUES.** On Claude Code, `/poteto-mode`'s route to figure-it-out now loads it through the Skill tool, 6 of 6 runs with and without compaction. On origin/main the same cases pass 0 of 6, because the lead reads the file instead. The branch changes several things at once. It drops the flag from 47 skills and installs the name-only listing. It rewrites poteto-mode's Principles paragraph to "Load every leaf and sibling skill this suite names yourself. On Claude Code, invoke it with the Skill tool". It rewrites pstack-harness's sibling-skill rule to "invoke it by name with the Skill tool", and poteto-mode's two figure-it-out route sentences to "load the **figure-it-out** skill". These runs cannot credit any one change alone, and the routed cases cover one skill and one prompt. Codex passes 6 of 6 on the branch; no Codex baseline ran. Two results need follow-up. A request that names no skill still loaded a gated skill in 1 of 3 runs on each harness. And deslop's hand-off to no-comments never ran on Claude Code, 0 of 9, in any of the three spellings, while Codex ran it in 3 of 9.

## What ran

The branch drops `disable-model-invocation` from 47 skills. Claude Code gets the name-only `skillOverrides` from setup-pstack step 0c (`skills/setup-pstack/scripts/skill-listing.py`), and Codex keeps `agents/openai.yaml` with `allow_implicit_invocation: false`. The four promises are new in this branch, and each case binds one of them:

| Case | Promise |
|---|---|
| `name-only-route-figure-it-out` (a) | `routed-skill-loads-when-named` |
| `name-only-unnamed-request` (b) | `name-only-skills-stay-unloaded-unnamed` |
| `name-only-route-after-compact` (c) | `routed-skill-loads-after-compaction` |
| `deslop-handoff-slash`, `deslop-handoff-bold`, `deslop-handoff-use` (d) | `deslop-hands-unsettled-comments-to-no-comments` |

The three (d) arms differ only in deslop step 5, through `skill_overlays`. `slash` keeps the shipped "go to `/no-comments`", `bold` says "go to the **no-comments** skill", and `use` says "needs a second review. Use the **no-comments** skill." The branch keeps the shipped text. The (d) fixture adds narrating comments to `rollup/__main__.py` and `rollup/export.py`, and one retry-header comment in `rollup/export.py` written to fall outside rules 1 to 3.

## Pins and runs

- Evaluator: the branch checkout that ran the runs moved from `bddc6369` to `56dfcd1e` during them, and the run files do not record it. Under `evals/promises` those commits differ only in two `ledger.json` claim strings, one of which adds the delegate route to the (d) promise.
- Skills pin, recorded in each `run.json`: `bddc636986225b4f2e669581d4bf06e4d3a76e4c` for the branch and `f8eb694f9c8b84b3bd4860cf65f59d9244c31aa5` (origin/main) for the baseline.
- Later commits change `skills/setup-pstack/SKILL.md`, `skills/poteto-help/SKILL.md`, README, PORTING, `evals/canon/{host,workspace}.py` and its README, `.github/workflows/upstream-sync.yml`, `tools/test_skill_invocation_policy.py`, `tests/skills/setup-pstack/scripts/test_skill_listing.py`, and the `PSTACK_SKILLS` scope of `skill-listing.py`. A run's installed tree holds only pstack skills, so the script provisions the same 47 names either way. That follows from the code; no run tested it.
- Command per group: `python3.14 evals/promises/live.py run --harness <h> --model <m> --effort <e> --skills-at <pin> --runs 3 --case <c> [--case <c>...] --out <dir>`. Groups ran in parallel; runs inside a group ran in sequence. No retries.
- Lead models the traces record: `claude-sonnet-5-5` at effort high on the adapter's pinned Claude Code 2.1.295, and `gpt-6-luna` at effort xhigh on Codex 0.162.0.
- Every branch run on Claude Code recorded `x_skill_listing` step `installed`. Every baseline run recorded step `absent`, since origin/main has no listing script.
- 13 of the 18 (a) and (c) runs hit the turn timeout: 3 of 6 Claude Code branch runs, 4 of 6 baseline runs, and 6 of 6 Codex runs. Every load happened before the timeout, so the verdicts stand. A timed-out run's reply stops at the timeout, so the hand-back check read only the reply text written before it.
- Durable copy: `.audit/guide-promises/live/name-only-listing/<group>/`, with the refusal probe in `probes/claude-refusal-main/` and the per-trace reads in `fail-reads.md`. A seq number below is a trace event number.

## Results

Counts are PASS of graded runs, three runs per cell.

| Case | Claude Code, branch | Claude Code, origin/main | Codex, branch |
|---|---|---|---|
| (a) routed load | 3/3 | 0/3 | 3/3 |
| (b) unnamed request | 2/3 | not run | 2/3 |
| (c) routed load after compaction | 3/3 | 0/3 | 3/3 |
| (d) `slash` arm | 0/3 | not run | 0/3 |
| (d) `bold` arm | 0/3 | not run | 2/2, 1 INCONCLUSIVE |
| (d) `use` arm | 0/3 | not run | 1/3 |

## Classification

- **(a) and (c), Claude Code branch.** Each run called `Skill(figure-it-out)` at seq 2 to 8, and the result succeeded. In (c) each run compacted on the `/compact` turn, from about 20k to 2.3k tokens, before the routed turn. A scan of the reply text found no hand-back to the user.
- **(a) and (c), origin/main.** No run called `Skill(figure-it-out)`. Each read `figure-it-out/SKILL.md` with `cat` or Read, as main's sibling-skill rule says, so the oracle grades "loaded by file read, not the Skill tool". The refusal text ("cannot be used with Skill tool due to disable-model-invocation. Ask the user to run /figure-it-out themselves") shows only when a lead calls the tool. One probe run, whose prompt told the lead to call it, shows it.
- **(a) and (c), Codex.** The lead read `figure-it-out/SKILL.md` whole with `cat`. In (c) the `/compact` turn ran with `model_auto_compact_token_limit=2000`, and each rollout recorded a compaction before the routed turn.
- **(b) FAILs, one per harness.**
  - Claude Code `relay-5fj2l7v9` ran `ls -R .claude`, then `cat` of show-me-your-work's SKILL.md, a skill that matches "log your decisions". The lead gave no reason.
  - Codex `relay-xo0lb9ub` ran `find .codex .agents -type f -maxdepth 4 -print`, then read show-me-your-work and the migration principle. The lead said it was "reading the repo's migration and decision log guidance" (seq 18).
  - A PASS Claude run also ran `ls -R .claude` and loaded nothing, so the scan alone does not explain the load. Claude Code's skill listing also shows each gated skill's bare name.
  - No load came from a description, which the listing hides on Claude Code and the policy file hides on Codex.
- **(d), Claude Code, 0 of 9.** Every run loaded deslop through the Skill tool, removed the five narrating comments, and kept the retry-header comment. No run called `Skill(no-comments)` or read its file, and nothing was refused.
  - In 4 runs the report passed the retry-header comment to no-comments in prose and stopped. Two put it under a heading that begins "Handed to `/no-comments`", and two said they left it for no-comments and unslop. deslop's Report section lists "Flags handed to ... `/no-comments`", which supports that reading.
  - In 4 runs the lead judged the comment settled. Three sent it to `/unslop` as deslop step 5 says of kept comments, and one kept it under rule 3.
  - In 1 run the lead left the call to the user.
  - Spelling made no difference. Each arm loaded no-comments 0 of 3.
- **(d), Codex, 3 of 9.**
  - In the three PASS runs, two in `bold` and one in `use`, the lead read no-comments. It said the retry-header comment needed review, then spawned `comment-sicko` at seq 46, 64, and 60. The comment was gone after that review. In `rollup-_sa5pilu` the comment-sicko child made the removal. In `rollup-ptemt433` the no-comments read went out in the same batch as the branch diff.
  - In the other six runs the lead cut the comment directly as narration under rule 1. Those were 3 in `slash`, 2 in `use`, and the INCONCLUSIVE `bold` run.
  - That INCONCLUSIVE run (`rollup-hyi433r6`) did read deslop. Its command chained a second `cat` of a path that does not exist, the chain failed, and the oracle could not credit the load, an oracle gap.
  - The bold-name spellings scored higher: `slash` 0 of 3, `bold` 2 of 2 graded, `use` 1 of 3. Three runs per arm cannot settle that.

## Follow-ups

- On Claude Code, 4 of the 9 leads treated deslop step 5 ("go to `/no-comments`") and its Report section ("Flags handed to ... `/no-comments`") as a request to name the comment in the report. If deslop must load no-comments, say so as an action in step 5, then rerun (d).
- On Claude Code, eight runs kept the retry-header comment as a real hazard or non-obvious behavior, and one cited rule 3. Most Codex runs cut it as narration. Use a comment that rules 1 to 3 do not settle on either harness, so (d) measures the hand-off alone.
- Count a chained read whose output shows the file, even when a later command in the chain fails.
- (b) loaded a gated skill without a name in the prompt in 2 of 6 runs, though never from a description. The guide's claim that these skills don't load from their description held in these 6 runs. The promise's further clause, "with no entry and no skill named, no agent in the run loads a skill whose agents/openai.yaml sets allow_implicit_invocation: false", did not.
