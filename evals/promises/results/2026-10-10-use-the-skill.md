# "Use the skill" live runs, 2026-10-10

**Status: ISSUES.** deslop now hands unsettled comments to no-comments on both harnesses. On the final skills tree the hand-off ran 3 of 3 times on Claude Code and 3 of 3 on Codex, against 0 of 9 on Claude Code and 3 of 9 on Codex on 2026-10-09. A control that keeps the new fixture and restores the old deslop wording ran it 0 of 6 times on Claude Code and 1 of 3 on Codex. The wording change is what moved Claude Code. The routed figure-it-out load holds at 3 of 3 on each harness. The first round of runs, at an earlier commit, found two regressions this branch caused. The branch fixed both before the final round. The request that names no skill did not improve: 1 of 3 per harness in each round. The new pstack-harness rule against loading skills found by listing never reached a lead before a load, because no lead had read pstack-harness by then.

## What ran

The branch rewrites sibling-skill load points as "Use the **name** skill" and defines using a skill once per CLI in pstack-harness. It adds a pstack-harness rule against loading a pstack skill found by listing or searching a skills directory. deslop step 5 tells the lead to use the no-comments skill on comments that rules 1 to 3 do not settle. The Report section lists what that skill did, where it used to list flags "handed to `/no-comments`". The (d) fixture's retry-header comment is now `# ask dana before changing this, we may want a header on every batch later`, a talk-to-the-owner note about our own code. The three (d) spelling arms collapse to one case, `deslop-handoff`, that runs the shipped text.

| Case | Promise |
|---|---|
| `name-only-route-figure-it-out` (a) | `routed-skill-loads-when-named` |
| `name-only-unnamed-request` (b) | `name-only-skills-stay-unloaded-unnamed` |
| `deslop-handoff` (d) | `deslop-hands-unsettled-comments-to-no-comments` |

Two arms ran from case files added to the evaluator worktree only. They are not in the repository. Copies are in `arm-cases/` beside the durable runs.

- `deslop-handoff-old-text` is `deslop-handoff` with three `skill_overlays` that restore the e4968e32 text of deslop step 5, the rule 3 sentence, and the Report line. The overlaid file is byte-identical to deslop at e4968e32.
- `name-only-route-cue` is `name-only-route-figure-it-out` with one overlay that adds "On Claude Code, that is a Skill tool call with the bare name, even when the listing shows only the name." to poteto-mode's Principles paragraph. The final tree ships that sentence.

## Pins and runs

- Round 1. The evaluator ran from a worktree detached at `034ef58791b1886c74e577fb6d72187e7c6931d5`, and the skills pin is the same commit.
- Round 2. The evaluator ran from a worktree detached at `881dcdd9cee24cf6769fdf8664be955ee4dc6315`, and the skills pin is the same commit. No later commit changes a file under `skills/`.
- Between the rounds, 26443774 renames `routing_decided` to `routing_events` and drops docstrings in `evals/promises/oracles.py`, with no change in behavior. 7e284616 restores the opening sentence of seven playbook steps. 881dcdd9 restores figure-it-out's Start sentence, adds the Claude Code sentence to poteto-mode, and narrows setup-pstack step 0c.
- Command per group: `python3.14 evals/promises/live.py run --harness <h> --model <m> --effort <e> --skills-at <pin> --runs 3 --case <c> --out <dir>`. Groups ran in parallel, and runs inside a group ran in sequence. No retries.
- Lead models: `claude-sonnet-5-5` at effort high on the adapter's pinned Claude Code 2.1.295, and `gpt-6-luna` at effort xhigh on Codex 0.162.0.
- Every Claude Code run recorded `x_skill_listing` step `installed`.
- Every (a) run hit the turn timeout, 300 s on Claude Code and 420 s on Codex, except one cue-arm run. Each load came before the timeout. A scan of every text event in all 15 (a) and cue runs with the oracle's `hands_back` found no hand-back to the user.
- Durable copy: `.audit/guide-promises/live/use-the-skill/<group>/`. Round 2 groups carry an `r2-` prefix, and `fail-reads.md` holds the per-trace reads. A seq number below is a trace event number.

## Results

Counts are PASS of graded runs, three runs per cell.

| Case | Claude Code, final (881dcdd9) | Codex, final (881dcdd9) | Claude Code, round 1 (034ef587) | Codex, round 1 (034ef587) |
|---|---|---|---|---|
| (a) routed load | 3/3 | 3/3 | 2/3 | 1/3 |
| (a) cue arm | not run | not run | 3/3 | not run |
| (b) unnamed request | 1/3 | 1/3 | 1/3 | 1/3 |
| (d) deslop hand-off | 3/3 | 3/3 | 3/3 | 2/2, 1 INCONCLUSIVE |
| (d) old-text control | 0/3 | 1/3 | 0/3 | not run |

## Classification

- **(d), Claude Code, 6 of 6.** Every run called Skill(deslop) at seq 1, read the diff, then called Skill(no-comments) between seq 7 and 9 and spawned comment-sicko. The dana note was gone after the review in every run, and two round 1 reports say Comment Sicko ruled it a note about our own code. Two runs passed only that comment in the Skill args.
- **(d) control, Claude Code, 0 of 6.** No run loaded no-comments, and the dana note survived every time. Each report named the comment for no-comments in prose, for example "Handed to `/no-comments`" and "Flagged for `/no-comments`". That is the 2026-10-09 failure, on a comment that every lead judged unsettled. The fixture change made the comment unsettled, and the step 5 action wording made the lead load the skill.
- **(d), Codex, 5 of 5 graded.** Each lead read deslop and then no-comments whole and spawned comment-sicko. Every edit to the dana note came after that review, and the note was gone at the end.
  - The round 1 INCONCLUSIVE run `rollup-tl62ryyy` did the same. Its first command chained `cat` of unslop and deslop with an `rg` that found no AGENTS.md and exited 1. The chain failed, so the oracle could not credit the deslop read, even though the output shows the file.
- **(d) control, Codex, 1 of 3.** One run read no-comments. Two cut the dana note directly as narration under rule 1 and reported no no-comments flags. Under the old wording the fixture is still settled by rule 1 on Codex 2 times in 3.
- **(a), final tree.** Claude Code called Skill(figure-it-out) at seq 2 or 3. Codex read figure-it-out whole at seq 7, and each worklist opens with figure-it-out's own items.
- **(a), round 1, Claude Code.** `relay-n5smwod9` read figure-it-out with the Read tool at seq 4 and never loaded pstack-harness. At that pin poteto-mode's Principles paragraph only pointed at pstack-harness. The cue arm put the Claude Code sentence back and called the Skill tool 3 of 3 times, so the final tree keeps that sentence. This is a partial step back from defining "use" only in pstack-harness.
- **(a), round 1, Codex.** All three leads opened an Autonomous run worklist, where the 2026-10-09 runs opened figure-it-out's. At that pin figure-it-out's Start began "Use the **poteto-mode** skill.", and the leads went back to pick a poteto-mode playbook. The final tree restores "Open a worklist whose first item is to read the Principles section of the **poteto-mode** skill." The two FAIL verdicts also rest on an oracle gap.
  - Each failed run read figure-it-out in a chained `cat` with a guessed path that does not exist, so the read went uncredited.
  - The oracle then took a later show-me-your-work read as the routing decision. In `relay-__ceheht` that read came from the same failed chain.
- **(b), 4 of 12 PASS.** In 7 runs the lead listed the skills folder (`ls -R .claude`, `ls .claude .claude/*`, `rg --files --hidden .agents .codex`, `rg --files -uu`, or `find .agents .codex`), then read gated skills by folder name. The skills were show-me-your-work, the migrate-callers principle, and technical-writing, which match "log your decisions" and "migration".
  - Claude Code had 4 of those 7 runs and Codex 3. No lead had read pstack-harness before the load. Two Codex leads read it later, because show-me-your-work points at it.
  - The eighth FAIL, Codex `relay-q9kyt_c6`, has no listing load. The lead loaded documentation-impact from its description and read pstack-harness. It then loaded technical-writing, which documentation-impact tells it to use. The new rule allows that load. The oracle counts only the prompt and delegate briefs as naming a skill, so it grades the run FAIL.
  - No load came from a description that the listing or the policy file hides.

## Follow-ups

- The listing rule lives in pstack-harness, which no (b) lead had read before its first gated load. It cannot act on a request that names no skill until it sits somewhere such a lead reads first. The promise's second clause, "no agent in the run loads a skill whose agents/openai.yaml sets allow_implicit_invocation: false", failed in 8 of 12 runs.
- Count a chained read whose output shows the file, even when a later command in the chain fails. This record has three more cases of it. In `routing_events`, do not count a read from a failed chain as a routing decision while the target skill's read in the same chain goes uncredited.
- In `name-only-skills-stay-unloaded-unnamed`, a skill that a loaded skill tells the agent to use counts as unnamed. That conflicts with the pstack-harness rule.
- Under the old wording, Codex cut the dana note as narration 2 times in 3. Under the shipped wording no Codex lead cut it before the comment review.
