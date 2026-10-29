---
name: interrogate
description: "Use for \"interrogate\", \"adversarial review\", \"multi-model review\", \"challenge this\", \"stress test this code\", \"find blind spots\", or \"tear this apart\". Adversaries try to break a change or design, and only findings proven by a run survive."
---

# Interrogate

Adversaries try to break a change or a design. A finding survives only when a run proves it. Report the findings. Do not apply fixes.

## Frame

The scope is what the user names. Otherwise it is the branch diff from its merge base with the base branch, through the working tree. State the intent. Use the **in-your-own-words** skill. Take the intent from the user's message, the commits, and the PR description. Ask the user when the intent is unclear.

## Fan out

Use the **arena** skill. Run its Phase A steps 3 and 4 and its Phase B, with four changes. Use the `interrogate reviewers` role in place of `arena runners`, one adversary per entry. Its default is one each on `fable`, `opus`, `sonnet`. Label the adversaries Adversary A, B, and so on to match the entry count, and put each label in its brief, so arms stay distinct when they share a model. Copy the scope's uncommitted changes into each worktree. Spawn each adversary as `general-purpose`. In place of the arena task and rationale, give each adversary the scope, the intent, and this brief:

> Break this change. Prove each finding with a run against the real code, such as a failing test, a repro script, or command output that shows the wrong behavior. For a design or plan, run a prototype or probe the current tree. Keep repros in your own worktree. Report each finding with a title, the exact command, the output it printed, and the output the intent requires. Leave out anything you did not run. That covers style, naming, structure, and risks that need a future change to matter. No findings is a valid result.

When the scope's context declares threats, add each declared threat to the brief and ask the adversaries to break its mitigation.

If a spawn rejects a default entry, also open a separate PR to update this step's default and `skills/setup-pstack/examples/pstack-models.md` in the pstack repository, the file the resolver reads. Do not block the review on the slug issue. Never treat an alias entry as a rejected slug.

## Verify

Verify each finding per arena Phase F by rerunning its command. Keep a finding when the output shows the failure and the failure breaks the intent. Drop the rest. Before you merge anything, state which models the adversaries ran on and count arms that shared a model as one adversary. Merge findings that share a root cause.

Skip arena Phases C, D, and E. Adversaries find different failures, so the verdict keeps every verified finding, not one adversary's list.

## Output

- **Intent**: the restatement.
- **Findings**: for each verified finding, the command, its output, how it breaks the intent, and the adversaries that found it. Say "no verified findings" when none survive.
- **Threats**: when the context declares threats, reconcile each with mitigation evidence or an explicit disposition per [Prove It Works](../principle-prove-it-works/SKILL.md).
- **Dropped**: for each adversary, the count of dropped findings and why.
