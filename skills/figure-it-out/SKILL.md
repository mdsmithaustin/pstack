---
name: figure-it-out
description: "Design an auditable playbook when no narrower one fits: a large migration, an ambitious multi-part change, or work a human reviews after stepping away. Scales rigor to the task, runs a hypothesis loop, and logs decisions. Use for /figure-it-out or 'figure it out'."
---

# Figure it out

When the task matches no playbook, design one. The deliverable before any code is the workflow itself: a sequence of phases that scales rigor to the task, runs the scientific method, and leaves a decision trail a human can audit after stepping away.

## Start

Open a worklist whose first item is to read the Principles section of the **poteto-mode** skill. Then add the phases below as items.

## Phase A: Frame

Ground first, then commit. Don't start the run until you can state:

- The definition of done as a falsifiable predicate. Call the Skill tool with `principle-prove-it-works`.
- The operation's recorded verification set. Read available memory, runbooks, and deploy scripts that name it. Include every applicable check in the minimum done predicate. Report each skipped item and its reason. An unavailable required check leaves the predicate unmet.
- A `worth doing` or `won't do` verdict for each requested item, with a brief reason tied to the project's design and the user's goal. Make these calls before sizing. A fit judgment does not cancel an explicit requirement. Record proposed exclusions and authorized scope changes separately.
- Scope, quantified for the accepted items. Size compared options on the same basis, including implementation, tests, documentation, generated files, and verification effort. Name exclusions and uncertainty, plus the blockers grounding surfaced.
- The rigor level, biased high. One-way doors and high blast radius get more. Reversible low-stakes steps get less. Rigor is gates and artifacts, not "try harder".

Track actual scope and effort against these estimates. When the chosen option exceeds a rejected option's comparable estimate, reassess the choice and report the overrun. Under an autonomy grant, continue within that grant unless an existing gate requires the operator.

Present the framing and tradeoffs before committing to a long run. Reversible work proceeds, but a multi-hour run earns one checkpoint. Call the Skill tool with `principle-never-block-on-the-human`.

## Phase B: Design the workflow

Decompose into atomic, independently-landable units. Sequence riskiest-unknown-first. Scaffold and verification come before features. Call the Skill tool with `principle-foundational-thinking`.

- Build the verification harness before the work, with the baseline captured from the pre-change state, so the check reads as "old value vs new value".
- For one-way-door design decisions, call the Skill tool with `architect` (it runs **arena**). Skip it for mechanical work whose shape is already concrete. A second arena over a settled design is over-engineering. Call the Skill tool with `principle-laziness-protocol`.
- Decide what fans out. Parallelize only across seams, and give each worker its own worktree or branch. Call the Skill tool with `principle-separate-before-serializing-shared-state`. Don't over-fan.
- Write the designed phase list down. That list is what the human reviews.

Then execute the design. Add its steps to the worklist as concrete items between the Phase C and Phase D entries. Run each under the Phase C loop discipline, and weave the Phase D log through them, a row as each step lands, rather than saving the whole trail for the end.

## Phase C: Run the loop

Each unit is an experiment. State the hypothesis, make the smallest change, measure against the predicate on the real artifact, keep it if it advanced, revert it if it didn't.
Call the Skill tool with `principle-sequence-verifiable-units`. Verify each unit before starting the next instead of batching checks at the end.

- Verify by inspecting the artifact, never a self-report. When something passes too easily, suspect the observation method before the system.
- Pair delegated work with a judge. If a worker games the gate, reset and harden the contract. If the gate itself is wrong, fix the gate in its own change rather than routing around it.
- For each new regression test, report the behavior it protects and evidence that it fails on the relevant defect before the fix and passes after it. A parent revision, safe targeted mutation, or failing fixture can supply the defect. Keep mutations in a disposable checkout. A setup or compiler failure does not prove the intended behavior failed. Reuse one run when it covers several tests. For other new tests, state the independent oracle and a plausible defect the test rejects. If a failing run is unsafe or unavailable, record the gap instead of claiming regression proof.
- A verdict is VERIFIED, NOT VERIFIED, or INCONCLUSIVE. Inconclusive is not a pass. Don't hide a negative.

## Phase D: Keep the audit trail

Call the Skill tool with `show-me-your-work` to log the run. Let that skill choose whether the trail stays local or is committed. Keep durable completion evidence available to the reviewer.

## Phase E: Verify and hand back

Check the whole against the Phase A predicate on the real product, not just the harness. Encode any recurring correction as a gate, a lint rule, a check, or a script. Call the Skill tool with `principle-encode-lessons-in-structure`.

Before handoff, link unresolved material defects and unmet requirements to existing tracker items or a checked-in known-issues file. Create missing records when authorized. Include the impact, evidence, current disposition, and owner when known. Filing a blocker does not satisfy the done predicate. If filing is unavailable or unauthorized, name that gap and the retained record.

**Reply:** the playbook you designed, the rigor level and why, the decision-trail path, what's verified against the predicate, and what's still open.
