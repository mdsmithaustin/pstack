# Suite outcomes and evaluation contract

This framework records the agreed purposes and evaluation policy. It connects
the existing documentation promises to evidence of useful work. It does not
change skill instructions, declare the suite effective, or implement new gates.
The agreed suite operating principles are recorded below. Numeric improvement
thresholds and their implementation remain open.

## Alignment status

Agreed on 2026-11-08 through the evaluation and suite discussions. This document
records the accepted decisions, not the interview transcript. Approval of these
principles is not approval of every existing workflow, delegation step, or review
cost. The [suite alignment assessment](suite-alignment-audit.md) maps these
decisions to existing mechanisms and distinguishes gaps from missing evidence.

Two principles were added on 2026-11-10 after that assessment was applied to
one playbook only. [Scope and rule ownership](#scope-and-rule-ownership) and
[Lead model floor and subtraction](#lead-model-floor-and-subtraction) record
them. Both are agreed design intent. Neither has runtime evidence yet.

## Two purposes

The skill suite's purpose is to deliver spec-correct, maintainable changes through
PR acceptance efficiently, while preserving correctness and code quality as
requirements evolve.

The evaluation system's purpose is to establish whether the suite consistently
keeps its promises and improves real work across supported harnesses, using the
cheapest trustworthy evidence, with deterministic checks wherever sufficient.

PR acceptance means required checks pass and required reviewers approve the
reviewed revision. Merge is a separate event. This measurement endpoint does not
replace the existing shipping playbook or shorten a user's requested task.

## Suite operating principles

### Scope and rule ownership

The principles govern the whole suite. Each rule has one owner, chosen by what
it decides. A playbook cites rules. It does not restate them or hold one that
another playbook needs.

| Owner | Owns | Loaded |
| --- | --- | --- |
| Router ([mode entry](../skills/poteto-mode/SKILL.md) and [task triggers](../skills/poteto-mode/references/task-triggers.md)) | How a task is run. This covers intensity, independent scrutiny, the stop rule, the effort budget, and the completion endpoint. | Always, before a playbook is chosen. |
| `principle-*` leaf skill | One judgment about the artifact, such as its design, tests, or complexity. | When its trigger arrives. |
| Shared reference, such as the [review lens](../skills/poteto-mode/references/review-lens.md) or [delegation](../skills/poteto-mode/references/delegation.md) | The procedure for applying a rule. This covers the questions, the evidence, and when to leave the code alone. | When the step arrives. |
| Playbook | The outcomes and their order for one task type. | When matched. |

Three consequences follow.

- A rule about how a task is run cannot live in a leaf or a playbook. It decides
  which leaves, agents, and steps load, so it applies before any of them.
- Where a leaf already owns a rule, the rule stays there. The test rule belongs
  to `principle-test-behavior-not-implementation`. The complexity rule belongs
  to `principle-laziness-protocol`. Proceeding on reversible work belongs to
  `principle-never-block-on-the-human`.
- A rule that two playbooks need belongs in neither. A principle implemented in
  one playbook is not implemented.

Some leaves describe both the artifact and the run, such as
`principle-prove-it-works` and `principle-sequence-verifiable-units`. Leave them
where they are until a demonstrated failure justifies a move.

### Lead model floor and subtraction

The router and every default route must work when the lead is a mid-tier model
at medium reasoning effort. On 2026-11-10 that means Claude Sonnet 5.5, GPT-6.1
Sol, or Grok 4.7, each at medium. A stronger lead is an upgrade, never a
requirement. No default route may depend on the lead holding hundreds of
standing instructions, choosing among dozens of similar skills, or tracking
evidence freshness from memory.

Design for the floor with one structure, not a branch per model tier.

- **Scripts carry what is deterministic.** Route selection from recorded facts,
  worklist creation, skill and gate lists, role resolution, brief assembly,
  evidence freshness, and format checks belong in small scripts that print the
  next action. Instructions carry judgment only. A script gives the same answer
  on every model and harness.
- **The lead decides little, and decides it early.** The lead supplies facts
  and judgment. It does not derive policy. Identification of a skill, a
  subagent role, an effort level, and a risk route must each be a short lookup,
  not a reading of the whole suite.
- **Less is more, and more so over time.** Models keep improving. An
  instruction that compensates for a model weakness is temporary. Record why it
  exists so it can be removed when the floor model no longer needs it.
- **Subtraction is a supported operation.** Subtraction means a route loads
  less. Taking a skill, gate, or rule out of what a route loads must be one
  small change. A structure that only makes addition cheap fails this
  principle.

This floor is a design target. No evaluation in this repository establishes
that the current router meets it. Structural choices made toward it rest on
published research, vendor guidance, and this repository's prior results, as
the [suite alignment assessment](suite-alignment-audit.md#reassessment-on-2026-11-10)
records. Report the floor as unverified until targeted evidence exists.

### Operating principles

Optimize both new work and maintenance of existing software. Measure them
separately so improvement in one does not conceal degradation in the other.
Greenfield features, prototypes, and investigations need acceptance criteria
appropriate to their purpose; code evolution also needs preservation evidence.

Keep the suite as small as possible while protecting promises and demonstrated
benefits. Size includes instruction volume, overlapping skills, runtime context,
repeated reviews, and maintenance burden.

Size is what a route places in the lead's context. We limit it for two reasons:
to protect the context window, and to avoid instructing a model where it already
works well. An instruction needs evidence that the floor model fails without it.
Moving text so that it loads only when needed reduces size. A skill that nothing
loads is waste, which is a separate cleanup concern.

Three measures follow, and they are not interchangeable.

- **Context** is the skill and reference Markdown a route makes the lead read,
  plus the text a script prints for it. `tools/check-route-bytes.py` reports it
  per route. Its counts are source bytes, which approximate tokens and omit
  reads a route makes only on a condition. What a session actually loaded is
  the true figure, and saved traces record it.
- **Need** is whether the floor model fails without an instruction. Bytes do
  not answer it. A short instruction the model does not need fails this test,
  and a long one it does need passes. Label each instruction as shown to help,
  shown not needed, or untested, and treat untested text as provisional.
- **Waste** is a skill that no step, trigger, or promise reaches.
  `tools/unused-skills.py` lists candidates for review and gates nothing.

Scripts, data files, and tests are maintenance surface. Their source never
enters the lead's context, so they are not size. They are still a cost to own,
and a new script needs the same evidence of an unmet need as a new skill.

Less code means avoiding maintenance cost without meaningful outcome value,
not optimizing line count. Tests must protect an identifiable behavior or
consequential failure and justify coverage that existing tests already provide.
Prefer assertions that survive behavior-preserving refactors. Complexity needs
a current requirement or demonstrated constraint. Preserve justified complexity
and useful tests even when deleting them would improve a size metric.

Orchestration should fit the task's risk and uncertainty. Use a lightweight,
standard, or intensive approach with an explicit reason for extra agents,
repeated attempts, or deeper review. These are route names in
`skills/poteto-mode/references/routes.md` for Bug fix, Feature, Refactoring,
and Perf issue. Other playbooks have one procedure. Set a task-specific effort budget and escalation
rule. If effort grows without useful evidence or progress, change the approach.
Ask the user when the next step changes agreed scope, cost limits, or authority.

Every code change needs independent scrutiny. Its scope and method depend on
immediate and accumulated risk, not just diff size. Existing human PR review can
satisfy that responsibility; another model reviewer is not always necessary.
A small review examines the diff and surrounding design. Structural warning
signs justify examining the component and its change history. Review the next
likely change using requirements and history, without speculative abstractions.

Task risk is grounded in observable evidence:

| Factor | Evidence |
| --- | --- |
| Consequence | Data loss, permissions, incorrect results, compatibility, and user-visible disruption. |
| Reach | Shared callers, public interfaces, dependencies, and affected workflows. |
| Uncertainty | Unclear requirements, unfamiliar code, weak tests, and behavior that cannot be reproduced. |
| Accumulated complexity | Repeated changes, growing conditionals, duplication, exceptions, recurring defects, and increasing repair effort. |
| Reversibility and detection | Failure visibility, rollback options, and whether recovery preserves data. |

Use Git history, dependency analysis, static checks, and existing test results
before commissioning model judgment. Unknown context is not low risk. Repeated
touches invite inspection; they do not prove deterioration. Deeper review follows
structural trends or consequential uncertainty, not an arbitrary edit count.
Calibrate any numerical thresholds from repository evidence.

Stop reviewing when acceptance criteria are satisfied and no material uncertainty
remains. Another pass needs a named unresolved concern. After repairs, recheck
affected behavior and newly exposed risks. Reuse valid evidence for unchanged
scope, keep missing evidence explicit, and honor repository-required gates.

The user's intent and persistent authorization determine completion. Investigation
ends with evidence; implementation can end at a reviewable PR; merging requires
the applicable authorization. Proceed autonomously on reversible work within
that boundary without repeating permission requests.

Support is specific to capabilities and workflows, not just skill installation.
Document alternatives only when they preserve the promise. Mark unavailable
workflows and unverified runtime behavior explicitly.

Before changing the suite, map each requirement to an existing skill, script,
check, or review step. Distinguish missing behavior, unclear instructions,
unreliable execution, and missing evidence. Prefer deletion, consolidation, or
deterministic enforcement when equivalent coverage is demonstrated. Measure
recovery effort as well as instruction and execution savings. Do not simplify
by silently narrowing promises.

## Existing promises and their evidence

The [guide ledger](promises/ledger.json) remains the source of guide claim IDs,
owners, and check assignments. Its [maintenance rules](promises/README.md) still
apply. This table connects representative promises to outcomes rather than
creating a second promise inventory.

| Existing documentation or promise ID | Intended outcome | Evidence still needed beyond the instruction |
| --- | --- | --- |
| [README introduction](../README.md): higher quality code, less code, confident parallel work | Maintainable work at justified total effort | Comparable completed tasks, structural analysis, and observed failures and costs. Fewer lines alone are not success. |
| `feature-settles-acceptance-tests-and-edges` | Spec adherence | Executable acceptance checks derived from requirements, including missing and invalid inputs. Following the planning step alone is insufficient. |
| `redesign-keeps-unchanged-behavior` | Preservation across successive changes | Prior behavior checks at each new requirement, with intentional changes identified separately. |
| [Guide principles](../docs/guide/08-principles.md) and `review-flags-unrequested-behavior-change` | Code quality and restrained scope | Structural analysis and independently reviewed examples at equivalent functionality. Naming a principle is a process observation. |
| `prove-it-works-checks-real-artifact` and `reply-carries-commands-and-outputs` | Trustworthy completion evidence | Actual execution against the intended artifact, valid and failing controls, and explicit unavailable evidence. |
| `shipping-verifies-each-pr-independently` and `documentation-impact-independent-review-pass-required` | Review readiness and acceptance | Revision-bound checks and review outcomes, rework, and elapsed and active effort. Invoking a reviewer does not establish review quality. |
| [Harness mapping](../skills/pstack-harness/SKILL.md) and harness-sensitive ledger entries | Consistent promises across supported runtimes | Separate evidence for Claude Code, Codex, Hermes, and Grok Build, with runtime versions and unsupported capabilities recorded. |

The README introduction is attributed upstream text. Its quality and parallelism
claims express the intended benefits, not a measured guarantee for every port
configuration. The guide ledger covers guide units, not every README sentence or
every possible suite outcome.

A static quote proves that an instruction exists. A script test proves the
tested script behavior. Neither proves that a model follows the instruction.
Live cases provide bounded behavioral evidence. Added value requires a separate
comparison against the same model, runtime, tools, and limits without the suite.
Compliance and benefit must remain separate in reports. A claim of reliable
added value needs both.

## Outcome measures

| Dimension | Measurement contract |
| --- | --- |
| Spec adherence | Report required behaviors satisfied, fully accepted tasks, and missed requirements by severity. Keep failed, incomplete, and non-loading attempts in the assigned population. |
| Code quality | Report complexity, duplication, dependency violations, and actionable review findings at comparable functionality. Static scores are indicators, not interchangeable definitions of maintainability. |
| Erosion | Track lost behavior and structural deterioration over successive requirements on the same codebase. Include the effort to implement the next change. A single final snapshot cannot establish the trajectory. |
| Delivery through acceptance | Measure task start to review-ready PR and to acceptance, accepted work per period, substantive rework rate, and time to resolve blockers. Separate active work from review queue time and compare similar task scopes. |
| Total effort | Account for human implementation and review time, elapsed time, tokens, and available cost across the lead, delegates, and gates. Mark missing accounting explicitly. |

These delivery measures are pre-merge analogues inspired by
[DORA's delivery metrics](https://dora.dev/guides/dora-metrics/). They do not
measure production deployment frequency, production failures, or recovery.
Controlled benchmarks isolate effects. Real PR observations are also required
for claims about delivery, with task difficulty and queue time recorded as
possible confounders.

No weighted total lets speed or structural scores compensate for a critical
failure or an unmet mandatory requirement. Each evaluation decision must name
its quality floors, smallest useful improvement, resource limits, and uncertainty
requirements before execution. Numeric defaults are not settled by this document.

## Evaluation policy

- Common acceptance criteria apply across supported harnesses. Native mechanisms
  may differ. Missing evidence is unverified, never inherited from another
  harness. Reports keep each harness visible and scope claims to tested versions.
- Individual promise checks and representative combined workflows answer
  different questions. Suite evaluations also examine conflicting instructions,
  duplicate reviews, and total effort from skill interactions.
- Routine CI uses deterministic checks. Behavioral changes require targeted model
  execution where fresh behavior is necessary. A deterministic grader can score
  that output without an additional model judge.
- Each recurring model evaluation names its decision, unique coverage, rerun
  conditions, and why cheaper evidence is insufficient. Each model judge names
  the judgment that executable checks cannot settle.
- Graders need known good and bad controls, including realistic defects. Version
  grader changes and calibrate subjective verdicts against independent human
  review so instrument changes do not appear as skill improvements.
- Automation may detect overlap and propose deterministic replacements. Before
  retiring coverage, demonstrate equivalent coverage and obtain independent
  maintainer review. Weakening criteria or narrowing promises also needs that
  review. A disappearing failure or a low recent failure rate is insufficient.

Periodic broader behavioral coverage is agreed policy, but its cadence, budget,
selection, and release enforcement are not implemented by this documentation
change. The current manual execution rules in [the eval guide](README.md) remain
in force. Missing required evidence must be reported as unverified.

## Ownership and independence

This repository owns its promises, representative tasks, fixtures, acceptance
criteria, and decisions to keep, change, narrow, or remove skills. `skill-ci` owns
reusable deterministic enforcement and orchestration. `skill-eval-harness` owns
reusable execution, evidence collection, grading, and comparison. Improvements
to shared capabilities belong in those projects and arrive here through published
pins. Existing local adapters do not imply that all machinery has migrated.

Slop Code Bench informed the discussion about iterative changes and erosion.
This repository must have no direct dependency on it: no required installation,
imports, CI integration, or dependence on its result schema. External benchmark
studies remain separate. Repository checks and measurements must work without it.

## Decisions and evidence required

Each evaluation must support a decision to keep, change, narrow, or remove a
skill or workflow. The decision record must identify the promise and its scope,
the behavior that would falsify it, the baseline, acceptance criteria, and the
assigned task population. Procedure compliance and outcome improvement are
separate results. Claims must narrow when evidence supports only a narrower scope.

A result justifies retaining a skill when it shows a worthwhile improvement over
the same model and deterministic tooling without that skill, within the declared
quality floors and effort limits. A skill can add value by preventing defects
earlier or reducing repair effort even when CI would eventually catch them.
A tool or review invocation alone does not establish that value.

Every advertised supported harness needs its own evidence for harness-dependent
behavior. Run selection follows the changed promise, triggering behavior, or
harness integration. Broader periodic coverage detects drift beyond those
selected cases. Unsupported capabilities and missing required results stay
visible as unverified. An aggregate cannot hide a failing harness.

Acceptance requirements and critical failures are release criteria to define
explicitly before a trial. Structural quality scores normally inform comparisons
rather than act as universal release thresholds. Existing release automation
continues to enforce its current rules until those criteria are implemented.

The evaluation system recommends decisions. Maintainers approve changes to
promises and coverage, with independent review before weakening them. Automatic
repairs must preserve the behavior being checked. Replacing model inspection with
a deterministic check requires both valid controls that pass and realistic
violations that fail, plus evidence that the replacement covers the same claim.
Preserve runtime cases for behavior the replacement cannot observe.

Real repository evidence complements controlled comparisons. Collect timestamps,
CI outcomes, and usage automatically where available, and sample human review
effort. Report task difficulty, queue time, and incomplete accounting. These
observations support delivery claims but do not alone isolate a skill's effect.

Shared tools must also prove fit for purpose: can they execute the intended
behavior, observe the promised outcome, distinguish missing evidence from a pass,
and account for the work they dispatch? Reuse an existing capability when it
meets that need. Repair a portable gap in its shared owner rather than adding a
parallel implementation in this repository.

## Current coverage and remaining decisions

The [coverage audit](coverage-audit.md), guide ledger, and maintained corpora
describe existing checks. Deferred ledger cases are recorded coverage plans,
not verified promises. The current audit reports them without failing solely
because they are deferred. The ledger's static category is not runtime proof.

The [closed efficiency pilot](results/2026-11-08-eval-efficiency.md) and other
historical comparisons retain their limits. This framework authorizes no fresh
model calls and claims no measured token savings.

The [port value comparison](port-value/results/2026-10-19.md) is the only
matched run that includes an arm without the suite. All three arms passed every
task, so it shows no benefit and no harm to acceptance. The current port arm
recorded 4,294,087 input tokens against 1,635,247 for native Codex and
1,541,349 for upstream pstack. It did not activate poteto-mode, used two
repetitions, and could not confirm whether parent usage includes child work.
Treat it as an observed cost of installed skills on those tasks, not as a
measured cost of the mode.

The suite principles above are settled. Follow-up must define representative
new-work and evolution cases, PR observations, thresholds, harness coverage and
cadence, and complete cost accounting. The source-level assessment identifies
implementation candidates; it does not authorize removing a promise or assert
that an existing workflow is ineffective. Existing procedure coverage does not
settle these outcome questions.
