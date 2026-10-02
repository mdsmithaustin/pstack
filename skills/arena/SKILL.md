---
name: arena
description: "Spawn N parallel candidates at the same task, pick a base, graft the strongest parts of the losers into it. Use for /arena, 'arena this', 'throw it in the arena', or when one attempt at a non-trivial artifact would lock in the wrong shape."
disable-model-invocation: true
---

# Arena

Fan out N parallel attempts at the same task. Read every candidate's rationale. Pick the strongest as the base. Graft the best ideas from the others into it. Verify the synthesized result.

## Start

Open a worklist with one entry per phase before launching anything.

1. Frame
2. Fan out
3. Cross-judge
4. Pick
5. Graft
6. Verify

## Phase A: Frame

The N candidates will receive the same prompt, so the prompt is the contract.

1. State the artifact each candidate is producing.
2. Derive the rubric. State what success looks like for *this* task, then turn it into 3-6 concrete gradeable criteria. For subjective criteria, use [Eval's criterion and calibration guidance](../poteto-mode/playbooks/eval.md). The rubric is the picker's tool in Phase D. Candidates only see the task.
3. Pick the runners. Use the `arena runners` role, one arm per entry. Its default is one each on `fable`, `opus`, `sonnet`. A rejected entry also follows the required-arm rule below. Spawn more when the arena covers multiple design directions. Same model N times when the work is generation-bound rather than judgment-sensitive. Spawn per **Spawn a role** in the **pstack-harness** skill, which resolves the role and builds this CLI's spawn call.
4. Assign output paths. Each candidate writes to its own location (a git worktree where possible, otherwise `/tmp/arena-<slug>/candidate-<n>/`), per the **separate-before-serializing-shared-state** principle skill.

## Phase B: Fan out

Spawn all N subagents in one message with `run_in_background: true`, each with the task, the path to the shared grounding, its own output path, and instructions to produce both the artifact and a short rationale.

Each rationale names the alternatives the candidate considered and what it rejected.

### Required arms

An arm or exact model requested for this task remains an obligation. If it cannot return a result, retain useful outputs but report the requested comparison as incomplete. Disclose substitutions and the models that actually ran. A replacement does not fulfill an exact model request. Configured defaults and role aliases resolve through the harness as usual. A default or discretionary candidate may drop out with a recorded limitation.

## Phase C: Cross-judge

After all Phase B candidates complete, choose one arm of the `arena cross-judge pool` role, resolved per **Spawn a role** in the **pstack-harness** skill. Its default pool is `fable`, `opus`, `sonnet`. Prefer a different model family or capability tier from the parent's. Spawn one readonly judge subagent on that model. It sees the rubric and the candidates by path label, scores each criterion, and recommends a base with rationale. It runs in parallel with the parent's reading in Phase D, not with the candidates themselves. Don't spawn the judge while candidates are still writing.

## Phase D: Pick a base

Read every candidate's rationale end to end before picking. Read a candidate's full artifact only when it is the base, or where you and the cross-judge disagree on a criterion. The cross-judge reads every artifact in full.

Score each candidate against the rubric criterion by criterion, not on holistic feel. Compare against the cross-judge. Agreement on the base confirms the pick. Disagreement means one of you is biased or the rubric was ambiguous. Read both rationales before deciding.

Pick the base on which candidate a future maintainer can extend most easily without breaking invariants. Prefer the cleaner boundary or smaller API when two feel tied, per the Laziness Protocol.

Record the pick and the reason in a short synthesis note alongside the base artifact, including the cross-judge's verdict.

## Phase E: Graft

Walk each losing candidate once more and identify what is worth porting into the base. The signal is usually one or two things per candidate, not most of it.

Fold each graft in by hand, per the **redesign-from-first-principles** principle skill. Don't paste mechanically. The result has to remain coherent under one mental model.

Record what was grafted, from which candidate, and what was rejected and why.

When N candidates converge on the same shape, that is a strong agreement signal. Note the convergence in the record and ship the consensus shape. No graft is needed. When N candidates wildly diverge, Phase A was under-specified. Reframe and re-run rather than averaging the divergence.

## Phase F: Verify

The synthesized artifact has to hold up under the same scrutiny as any other output, per the **prove-it-works** principle skill.

If verification surfaces a problem the arena did not catch, either Phase A was wrong (re-frame and re-run) or one candidate caught it and you missed the graft (go back to Phase E). Don't paper over.

## Outputs

One synthesized artifact. One short synthesis note alongside, naming the base, the grafts (with source candidate), the rejections, the dropouts if any, and the verification result.
