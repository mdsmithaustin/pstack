# Suite alignment assessment

Source-level assessment on 2026-11-08 against commit
`3dfcb0c7d47a5c48675bb75d23b264ffa51dd3c3`, using the subsequently agreed
[suite operating principles](framework.md#suite-operating-principles).
This assessment inspects instructions and existing evaluation documentation.
It does not establish runtime compliance, quantify savings, or approve deletion.
No model benchmark calls were run.

## Existing mechanisms and gaps

| Agreed requirement | Existing mechanism inspected | Assessment and smallest next action |
| --- | --- | --- |
| Optimize new work and existing-code evolution separately | [Feature](../skills/poteto-mode/playbooks/feature.md) handles both new and existing projects; [Refactoring](../skills/poteto-mode/playbooks/refactoring.md) pins behavior and requires a reader-load improvement. | Existing workflow coverage. Separate outcome reporting and representative change sequences still need definition. Reuse these workflows rather than add another. |
| Tests protect behavior and avoid unnecessary maintenance | [Test Behavior, Not Implementation](../skills/principle-test-behavior-not-implementation/SKILL.md) applies two counterfactual edits and permits deleting useless tests; the [review lens](../skills/poteto-mode/references/review-lens.md#tests-principle-test-behavior-not-implementation) accepts existing coverage for structure-only changes. | Strong instruction coverage. Refactoring step 1 also tells the agent to write a characterization pin. Clarify reuse of an adequate existing pin before adding tests. Duplicate coverage is not consistently justified by these instructions. |
| Complexity needs outcome value | [Laziness Protocol](../skills/principle-laziness-protocol/SKILL.md), Feature's shape step, and [Architect](../skills/architect/SKILL.md) reject indirection without a purpose and recognize legitimate complexity. | Already covered in instructions. Test application before adding prose. The structural lens's file-size threshold is a smell with an exception, not evidence that fewer lines always improve quality. |
| Preserve behavior as requirements evolve | [Redesign From First Principles](../skills/principle-redesign-from-first-principles/SKILL.md), Feature, and Refactoring require preserving unrequested behavior and invoke `preserve.py`. | Existing instruction and executable mechanism. This does not measure long-term erosion or prove support for every project test runner. Keep preservation and structural quality as separate outcomes. |
| Every code change receives independent structural scrutiny | Feature's Proven step requires an independent spec reviewer. [Code review](../skills/poteto-mode/playbooks/code-review.md) applies the structural lens; [Opening a PR](../skills/poteto-mode/playbooks/opening-a-pr.md) handles publication. | Partial fit. A spec-only reviewer is not automatically an independent structural reviewer. The inspected paths do not establish one common rule for crediting existing human review or verifying structural-review coverage for every code change. Reuse the review lens and existing reviewer before adding a panel. |
| Review accumulated complexity and the next likely change | Architect's scrap criteria recognize repeated workarounds; the review lens detects repeated branching; [Correct](../skills/correct/SKILL.md) mines commits, reverts, and review comments for recurring mistakes. | Useful ingredients exist. No common history-based trigger was found in the inspected Feature, Refactoring, Code review, Architect, and review-lens paths. Connect existing history evidence to review depth; do not add a fixed number-of-touches gate. |
| Proportionate orchestration and effort limits | Feature delegates at three source files or two workstreams and explicitly calls this an unmeasured default. Architect compares alternatives; [delegation](../skills/poteto-mode/references/delegation.md) selects roles. | Current thresholds measure size and decomposition, not the agreed risk factors. Reasoning-effort settings are not a total task budget. Compare lighter execution within existing workflows before replacing these defaults. |
| Stop when evidence is sufficient and reuse valid review | [Documentation impact](../skills/documentation-impact/SKILL.md) retains unchanged review coverage and bounds repair rounds. Code review repeats its aggregate deslop pass after fixes or base changes. [Autonomous run](../skills/poteto-mode/playbooks/autonomous-run.md) stops at its predicate and pivots at plateaus. | Partial fit. Documentation review offers an existing model for scoped rechecks. General review reuse and task-wide effort escalation need explicit ownership. Do not remove independent checks merely because multiple steps mention review. |
| Completion follows user intent and authorization | [Poteto-mode](../skills/poteto-mode/SKILL.md) distinguishes investigation from implementation and respects a user's explicit refusal, but also requires commit, push, and PR steps without being asked. | Potential contract tension. Negative overrides are explicit; a positive requested completion boundary should also govern publication. Any repair belongs in the central routing/completion rule, with affected guide promises reviewed. |
| Support means demonstrated capability | [Harness mapping](../skills/pstack-harness/SKILL.md) uses live tools as authoritative, selects action-specific adapters, and records limitations. [Promise checks](promises/README.md) distinguish inconclusive and deferred evidence. | Existing mechanisms. A capability-by-workflow evidence view remains needed before broad support claims. Installing or loading a skill is insufficient evidence. |
| Keep the suite small without losing promises | Laziness Protocol and [Subtract Before You Add](../skills/principle-subtract-before-you-add/SKILL.md) favor removal. Correct drops rules when structural enforcement replaces them; [Reflect](../skills/reflect/SKILL.md) requires controls and CI before retiring overlap. | Much of the policy already exists. The [coverage audit](coverage-audit.md) covers evaluation overlap, not proof that particular skills or review stages can be removed. Measure instruction and runtime effort plus recovery cost before consolidation. |

The review lens and [structural quality reference](../skills/interrogate/references/code-quality-review.md)
can assess evidence-grounded maintainability concerns. [Interrogate](../skills/interrogate/SKILL.md)
requires an executed reproduction and excludes risks that need a future change
to matter. It therefore cannot substitute for the entire structural review.
Keep those responsibilities distinct rather than duplicating adversarial panels.

## Simplification candidates, not approved removals

1. Reuse existing behavioral coverage as the refactoring pin when it already
   establishes the required contract. Retain a new pin when coverage is missing.
2. Let one appropriately briefed independent review cover the relevant spec and
   structural questions where it can do both reliably. Compare this with separate
   reviews before consolidation; different failure detection may justify both.
3. Carry revision-bound review evidence forward for unchanged scope, using the
   existing documentation-review rules as a starting point. Reopen affected
   coverage when code or context changes.
4. Use existing history inspection and structural checks to select review depth.
   Avoid a new risk-scoring skill or a model-scored risk evaluation on every task.
5. Keep each judgment rule in its existing principle or review reference. Repair
   routing and evidence reuse before copying rules into more playbooks.

None of these candidates justifies dropping a promised check now. An instruction
match is not a runtime success, and a repeated instruction is not automatically
redundant: routing, discovery, and recovery may depend on it.

## Ownership and follow-up

| Work | Owner and evidence needed |
| --- | --- |
| Reconcile completion boundaries, review responsibilities, pin reuse, and escalation | Existing pstack mode, playbooks, and review references. Show the current failure on a representative case, then verify the smallest repair and preservation of affected guide promises. |
| Quantify suite size and recurring overlap | Reuse source inventories, coverage policy, and saved traces first. Count instruction bytes, loaded context, repeated checks, and available execution usage separately. Tokens alone cannot establish equivalent quality. |
| Collect portable usage and review evidence | Assess the shared harness's existing capabilities before changing it. Portable execution, trace parsing, grading, and reporting belong in `skill-eval-harness`; reusable deterministic enforcement and dispatch belong in `skill-ci`. This source review did not audit those projects' implementations. |
| Establish new-work and evolution outcomes | Repository-owned tasks and acceptance criteria, with matched baselines and separate populations. Add real PR observations for delivery claims. No direct Slop Code Bench dependency. |
| Demonstrate consolidation preserves value | Known-good and known-bad controls, targeted behavioral comparisons where needed, independent review, and total effort including recovery. Keep unsupported outcomes unverified. |

The next implementation decision should select one demonstrated gap and its
smallest existing owner. Numerical budgets, risk thresholds, benchmark population
sizes, and broad recurring schedules remain unset. This assessment recommends
no new skill and makes no measured savings claim.
