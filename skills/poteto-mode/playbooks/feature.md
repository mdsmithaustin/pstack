### Feature

**You own the design. Plan, review, verify.** Delegate implementation. Stay in the lead.

Run every step in order. Skip a step only as the Playbooks paragraph of the poteto-mode skill allows, and mark it `skipped: <reason>` with a reason that covers that step alone. Where a step says how to run in a new project, run it that way instead of skipping it.

1. `how` over the affected subsystem. Use the **how** skill, and ask it to list the components, hooks, helpers, and UI patterns the repository already has for this job. Reuse them in the design and the step 4 brief. Extend a shared one only when every caller keeps its behavior. Give the reason for each new one. In an empty or new project, run the step anyway and record `no existing code` as its outcome.
2. `architect` for parallel design exploration when the change crosses a function boundary or admits several valid shapes. Use the **architect** skill for it. A small, self-contained change keeps this step with `skipped: <reason>`.
3. Write the throughput checkpoint as four items in the same worklist. A dimension that does not apply (single file, no fan-out) still gets its item, marked `skipped: <reason>`:
   - **Blocking first steps.** Gates run before fan-out.
   - **Independent workstreams.** Disjoint files, services, or layers parallelize. Shared writes serialize.
   - **Shared mutable state.** Default to splitting the target (the **separate-before-serializing-shared-state** principle skill). Serialize only for real invariants.
   - **Smallest safe decomposition.** If one worker is best, name why.
4. Delegate code-writing to a subagent on the `feature` role with a specific scope (file paths, named data shape and its organizing structure per **principle-model-the-domain**, a state machine over scattered booleans, a table/registry over branching, a typed model over repeated shape assumptions, chosen before the delegate writes logic, and success criteria). Use the **pstack-harness** skill's **Spawn a role** section to resolve the role. Carry the checkpoint's independent workstreams into the briefs. Disjoint file sets get one delegate each, spawned at this level in one message. Coupled work gets one owner whose brief names the split it may make. When the implementation admits multiple valid shapes (error handling, abstraction layer, test structure), use the **arena** skill to delegate instead, so the runners surface the alternatives and the cross-judge guards the pick. Mandatory: no skip-with-reason escape, and Laziness Protocol does not override it (the gain is review separation, not lines saved). A subagent forbidden to spawn satisfies this by owning the diff directly with the same review separation. No "standing by" reply that waits on a nested agent. Comments per **Comments**. Surgical edits, re-ground against the source for upstream-derived files. Port shared-primitive improvements to all consumers and verify each. Commit liberally, unless the user said not to commit, and put that instruction in the brief.
   Parent-level fan-out also covers slices that produce independent artifacts (audits, cross-subsystem investigations, competing experiments). Rewrite the checkpoint at phase boundaries. A phase boundary gets a fresh delegate with consolidated scope, never a resume of the last one.
5. Verify on the matching surface against the accepted scope and integrated result, per [Prove It Works](../../principle-prove-it-works/SKILL.md). "Inconclusive" or wrong-surface is not a pass. Flag it.
   Then check the integrated diff against the existing code for departures. Look for:
   - a new component, hook, helper or test helper where one already does the job;
   - a hand-built version of a shared UI piece;
   - a visual choice that differs from nearby screens, such as button variant, row layout, spacing, color or empty/error/loading state;
   - a show/hide or focus behavior that differs from what the replaced or neighboring UI did.

   Search the repository for each. An existing pattern records an earlier taste decision, so overruling one has to be visible.
6. Rebase into small, ordered commits. Stack follow-ups. In an existing repository, commit on the branch that the **Worktree** rule in `playbooks/opening-a-pr.md` sets up, never on main. If the project has no git repository, run `git init` in the directory that holds all of its files, usually the working directory, and commit on its first branch.
   Use the **sequence-verifiable-units** principle skill, building, verifying, and committing each small unit before the next.
7. If the design is contested, use the **interrogate** skill before shipping. Otherwise mark this step `skipped: <reason>`.
8. Run **Opening a PR**. If the task has no commits to propose, or the repository has no remote, mark this step `skipped: <reason>`.

**Reply:** what you built, what you chose and why, the throughput checkpoint, open decisions, and **Departures from existing patterns**. For each departure, give the pattern it overrules, where that pattern lives, and why the change overrules it, or write None. Carry the same section into the PR body. Tables for design alternatives.
