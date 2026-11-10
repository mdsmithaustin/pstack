# Suite alignment assessment

Source-level assessment on 2026-11-08 against commit
`3dfcb0c7d47a5c48675bb75d23b264ffa51dd3c3`, using the subsequently agreed
[suite operating principles](framework.md#suite-operating-principles).
This assessment inspects instructions and existing evaluation documentation.
It does not establish runtime compliance, quantify savings, or approve deletion.
No model benchmark calls were run.

The table below describes commit `3dfcb0c`. Its Feature rows are out of date.
The [reassessment on 2026-11-10](#reassessment-on-2026-11-10) covers the whole
suite at commit `6ec0c01` and adds the two principles agreed that day.

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

## Reassessment on 2026-11-10

Source-level reassessment of the whole suite at commit
`6ec0c0147253875bea4fdebadfc96e01a23d930c`, against the framework including
[scope and rule ownership](framework.md#scope-and-rule-ownership) and the
[lead model floor](framework.md#lead-model-floor-and-subtraction). No model
calls were run. The recommendations rest on source inspection, this
repository's prior results, published research, and vendor guidance. They are
design choices to review, not measured improvements.

### What changed since the first assessment

Commit `6ec0c01` added a risk-based compact route, credit for existing human
review, review reuse after repairs, and an accumulated complexity check. All
four landed in [Feature](../skills/poteto-mode/playbooks/feature.md) and the
[review lens](../skills/poteto-mode/references/review-lens.md). Bug fix,
Refactoring, Perf issue, and the always-on task triggers did not change. The
agreed principles therefore hold on one route.

### Facts that needed a whole-repository reading

No single file states the facts below. Each one took several files to
establish, so they are recorded here with the command or path that reproduces
them. Byte counts are UTF-8 source bytes at the commit above. They are not
provider tokens.

**What the router loads before it reads any code.**

| Item | Size | Source |
| --- | --- | --- |
| Mode entry | 15,904 of a 16,000 byte budget | `python3 tools/check-mode-entry-size.py` |
| Entry, Playbooks section | 7,798 bytes. Its first paragraph holds 26 sentences of rules. | `skills/poteto-mode/SKILL.md` |
| Entry, Principles section | 5,746 bytes listing 24 leaves with a trigger each | Same file |
| Task triggers | 9,177 bytes, 25 triggers, read on every invocation, resume, and scope change | `references/task-triggers.md` |
| Sentences in entry plus triggers | About 280 | Counted by sentence terminator |

**Gates that run on every code task, whatever its risk.**

| Gate | Frequency | Stated in |
| --- | --- | --- |
| Restate the goal | First message and each final report | Task triggers |
| `unslop` | Every prose surface, the reply included | Entry and task triggers |
| `deslop`, with a complete reread of its 10 KB file and retained evidence | Every commit or amend, including work-in-progress commits | Task triggers, Opening a PR, [deslop](../skills/deslop/SKILL.md#before-each-commit) |
| `unslop` over comments, names, and messages | Every commit | Task triggers |
| `technical-writing` | Every commit body, PR title, and PR description | Task triggers and Opening a PR |
| `preserve.py` | Every commit | Entry |
| `no-comments` | Before review, when comments or suppressions changed | Task triggers |
| `documentation-impact`, then a different-agent review when it asks for one | Before reporting a substantive change complete | Task triggers |
| `pr-recap` | After a PR opens and after every push that changes its diff | Task triggers and Opening a PR |

Opening a PR also says to commit liberally, which multiplies the per-commit
rows. A compact Feature that ends in a pull request still reads about 155 KB
of instructions across the entry, triggers, playbook, harness skill, and these
gates. That figure is a sum of the files' sizes, not an observed trace.

**Independent scrutiny by playbook.** Feature requires it and can credit human
review. Bug fix, Refactoring, and Perf issue name no independent reviewer and
no rule for crediting one. Their lead reviews a delegate's diff, which is not
independent of the plan.

**Fixed intensity by playbook.** Bug fix directs the lead to delegate both
investigation and the fix and to spawn two subagents before reading source.
Refactoring makes 11 skill calls, always writes a new pin, and always delegates
the mechanical edits. Neither has a lighter route.

**Skill visibility.** All 65 skills are model-invocable by frontmatter.
`agents/openai.yaml` withholds 54 from implicit invocation on Codex. Claude
Code ignores that file, so the same gating exists there only after
`/setup-pstack` writes name-only listing overrides. Eleven skills list with
full descriptions on both. `ls skills/*/agents/openai.yaml` reproduces the
count.

**Cost of removing a skill.** A skill's name appears in many files outside its
own directory. `git grep -l <name> -- . ':!skills/<name>'` reports 57 files for
`unslop`, 48 for `deslop`, 34 for `no-comments`, 27 for `documentation-impact`,
23 for `technical-writing`, and 16 for `pr-recap`. No manifest lists what
depends on a skill.

**Promises per owner.** Inverting `owners` in the [ledger](promises/ledger.json)
gives 55 promises on the mode entry, 52 on `setup-pstack`, and 48 on
`pstack-harness`. `pr-recap` owns none and has no corpus, yet it runs on every
push. `verify-commands` and `runtime-probes` own none in the ledger but have
their own corpora.

**Deterministic helpers that already exist.**

| Script | What it decides without a model |
| --- | --- |
| `setup-pstack/scripts/check-models-config.py --resolve` | Role to model and effort, per harness |
| `pstack-harness/scripts/subagents.py brief` | A persona's complete briefing text |
| `pstack-harness/scripts/preserve.py` | Whether the start commit's tests still pass |
| `pstack-harness/scripts/read-plan.py` | Commands that read a file within an output cap |
| `pstack-harness/scripts/loading-path.py` | Files and bytes one harness action loads |
| `poteto-mode/scripts/check-plan.mjs` | Whether a multi-phase plan has the required structure |
| `poteto-mode/scripts/orch` | Durable unit, ledger, and inbox state for Orchestrate |
| `poteto-mode/scripts/watch-pr` | PR state, merge gate verdict, failed check evidence |
| `tools/check-mode-entry-size.py` | The entry's byte budget |

Route choice, worklist creation, gate selection, brief assembly, and evidence
freshness have no script. The lead performs each from prose.

**Lead models in the evidence.** Results name Sonnet, Opus, Fable, GPT-6.1 Sol,
and Grok 4.7 Build in different waves. No ledger field records which lead model
and effort verified a promise. The suite's fit for a mid-tier lead at medium
effort cannot be read from existing results.

### Assessment by principle, whole suite

| Principle | State at `6ec0c01` | Gap |
| --- | --- | --- |
| Scope and rule ownership | Risk route, review credit, and review reuse live in Feature. One design-smell sentence is copied in Feature and Refactoring. The preserve command appears in 9 files. | Run rules sit in a playbook. Other playbooks cannot cite them. |
| Purpose, new work and evolution measured separately | Unchanged. Workflows exist. Separate populations do not. | Evidence gap, not an instruction gap. |
| Smallest suite | 65 skills and 834 KB of Markdown under `skills/`. The entry sits at 99 percent of its byte budget. | The budget is a ceiling being approached. Nothing ratchets size down or reports bytes per route. |
| Tests and complexity | Leaves own these rules. Refactoring still orders a new pin when coverage may already exist. | One sentence in Refactoring step 1. |
| Proportionate orchestration, budget, escalation | Feature only. No playbook sets a task budget or an escalation rule. | Router owns none of this. |
| Independent scrutiny scaled to risk | Feature only. | Bug fix, Refactoring, and Perf issue have no scrutiny rule. |
| Stop and reuse evidence | Documentation impact and Feature reuse evidence. `deslop` repeats in full on every commit. Code review repeats its aggregate pass after any fix or rebase. | Freshness is judged from prose and memory. |
| Completion follows intent | The entry runs commit, push, and PR steps without being asked. Only a refusal changes the endpoint. | A stated endpoint does not govern publication. |
| Support is demonstrated | Unchanged. | No capability-by-workflow view. |
| Evidence before change | Both matched baselines were saturated. | No task has headroom to show benefit. Not addressed here by design. |
| Lead model floor | The entry and triggers hold about 280 standing sentences. The lead chooses among 25 playbooks and 24 principle triggers, assembles briefs from about ten required clauses, and tracks evidence freshness itself. | The design assumes a top-tier lead. |
| Subtraction | Removal touches 16 to 57 files. No dependency manifest, no removal check, no record of why a compensating instruction exists. | Addition is cheap. Removal is expensive. |

### Recommendations

The work is ordered so that each phase is a small, reviewable change that the
next one builds on. Phases 1 and 2 remove more text than they add. No phase
adds a skill.

**Phase 1. Move run rules to the router.** Instruction edits only.

1. Move the risk record and the route choice out of Feature into the Playbooks
   section of the mode entry. Name three routes, lightweight, standard, and
   intensive. Feature's compact route becomes lightweight.
2. Add a lightweight route to Bug fix, Refactoring, and Perf issue by citing
   the router rule. Lightweight means direct work by the lead, no panel, and
   only the leaves the step needs.
3. Move the paragraph that credits existing review or briefs one
   `trail reviewer` from Feature step 7 into the review lens. Each code-changing
   playbook's Proven step links it.
4. Add two fields to the opening worklist item for every playbook. `endpoint`
   takes evidence, local commits, pushed branch, reviewable PR, or merge. A
   stated endpoint governs, including a host instruction such as "do not open a
   pull request unless asked". Without one, the default is the furthest
   reviewable state the repository supports, as the
   [default endpoints](#default-endpoints) table lists. `budget` names what
   would make the lead change approach.
5. State once, in the router, that another review pass needs a named
   unresolved concern.
6. In Refactoring step 1, reuse an adequate existing pin before writing one.

**Phase 2. Make routing a lookup.** One manifest and one script.

1. Add `skills/poteto-mode/routes.json`. For each playbook it lists the steps,
   the skills each step loads, the gates, and which routes include each. It is
   the only place a playbook step names a gate skill.
2. Add `skills/poteto-mode/scripts/plan.py`. The lead passes the playbook and
   five categorical risk facts, each `low`, `material`, or `unknown` with one
   line of evidence. The script prints the route, the worklist items with
   their outcome sentences, the loads for each step in the current harness's
   own wording, the gates, the scrutiny requirement, and the endpoint and
   budget fields to fill. `unknown` never yields lightweight. The table runs
   on every task. [Route selection](#route-selection) gives the order and the
   overrides.
3. Add `skills/poteto-mode/scripts/risk-facts.py`. It gathers the evidence a
   command can gather: commit count and churn on the touched paths, caller
   count, and whether tests cover them. The lead judges consequence and
   uncertainty. This follows the framework's order of Git history and static
   checks before model judgment. [Reach evidence](#reach-evidence) gives its
   GitNexus and grep rules.
4. Cut the mode entry to a contract, a playbook table, and the instruction to
   run `plan.py`. Remove the Principles list from the entry, since the plan
   names each step's leaves. Lower the entry budget in
   `tools/check-mode-entry-size.py` from 16,000 to 8,000 bytes.
5. Put the nine daily routes in the entry table: Investigation, Code review,
   Bug fix, Feature, Refactoring, Perf issue, Prototype, Babysit, and Shipping.
   Move the program, session, and specialty routes to one linked table.
6. Fold the always-on task triggers into the manifest's gates. Keep in prose
   only the triggers that need judgment.

**Phase 3. Gate by evidence, not by repetition.**

1. Add `pstack-harness/scripts/gate.py` with `record` and `check`. It stores
   the gate name, the Git tree ID, and the result under `.git/pstack/`. `check`
   answers whether a gate's evidence still describes the current tree and
   which paths changed since. The lead stops judging freshness.
2. Run `deslop`, comment `unslop`, and `technical-writing` once per published
   head on the lightweight and standard routes. Keep per-commit runs for the
   intensive route and for machine-consumed playbooks.
3. Drop the rule that rereads all of `deslop` before each pass. `gate.py`
   records that the pass ran against a tree.
4. Move the mechanical writing rules to a lint: the long dash, the mid-sentence
   colon, the Conventional Commits title, and the required PR body headings.
   Keep `unslop` and `technical-writing` for what a pattern cannot judge.
5. Run `pr-recap` when the user asks or the repository opts in. It owns no
   promise and has no corpus.
6. Move Gated publish, Snapshot cleanup, and Gated merge preparation out of
   Opening a PR into a reference that loads only when the gate is detected.

**Phase 4. Delegate up or out, never sideways.**

1. State one spawn rule in delegation. Spawn for parallel independent streams,
   for bulk reading that would fill the lead's context, for independent
   scrutiny, or to send a named hard problem to a stronger model. A single
   stream on the lead's own tier stays with the lead.
2. Keep the reviewer at or above the lead's tier. A mid-tier author with a
   stronger reviewer is the pairing to protect.
3. Extend `subagents.py brief` to print the required brief clauses from its
   arguments: the source path, start commit, branch, preserve command, commit
   evidence rule, and attended state. The lead adds scope and judgment.
4. Reserve the three-arm panels in `arena`, `architect`, and `interrogate` for
   the intensive route.

**Phase 5. Make subtraction cheap, then subtract.**

1. Add a removal check to the lint tier. For each routed skill it confirms the
   name appears only in the skill's directory, the manifest, generated lists,
   and the ledger.
2. Add `ledger.py owners --invert` so a skill's promises are one command away.
   A unit with no promise and no corpus is a removal candidate by default.
3. Extend `loading-path.py` to report bytes per route from the manifest. Add a
   budget per route that CI lets only tighten.
4. Record in `PORTING.md`, for each port addition that compensates for a model
   weakness, the failure it answers, the model, and the date. Review the list
   when the floor model changes.
5. First candidates, each needing the framework's independent maintainer
   review: `pr-recap` as a default step, the per-commit `deslop` reread, the
   Principles list in the entry, and the copied design-smell sentence.

**Phase 6. Record what is supported.** This phase adds records. It authorizes
no runs.

1. Add `lead_model` and `lead_effort` to live result records so later targeted
   runs can show which promises hold on a mid-tier lead.
2. Generate a capability-by-workflow table from existing results, one column
   per harness. Mark a cell verified only where a result for that harness
   exists, and unverified otherwise. Link it from the README's support
   statement. Several results files record Hermes and Grok Build lanes as
   inconclusive or not run, so the four-harness claim currently has no single
   place that shows its evidence.

#### Route selection

The lead that runs the task judges the facts. The table applies the policy. No
separate model chooses the route.

1. `risk-facts.py` gathers churn, callers, and coverage for the touched paths.
2. The lead records the five facts as `low`, `material`, or `unknown`, each
   with one line of evidence.
3. `plan.py` maps the facts to a route through a fixed table. This step always
   runs and needs no model.
4. An optional decision call can check the lead's answers. It reuses the
   locked-down, tool-less CLI call that the
   [bot-triage comparison](bot-triage/README.md) uses. It receives the same
   packet and rates the same five facts. It runs only when the script's
   evidence and the lead's answers disagree, such as low reach recorded on a
   path with many callers.

The decision call can raise the route. It cannot lower it. An unavailable or
malformed answer leaves the table's result in place, as that runner already
treats `unavailable` as no answer. The call ships switched off. A repository
turns it on after its own comparison results give confidence in the call. The
runner has adapters for Codex and Claude Code only, so the table must be
sufficient alone on every harness.

Overrides follow three rules.

- The user can set the route in either direction. The worklist records it as
  `route: <name> (user)`.
- The lead can raise the route with a stated reason. It cannot lower the route
  below the table's result.
- No override skips a repository-required gate or the authorization that an
  irreversible action needs.

#### Reach evidence

`risk-facts.py` follows the convention the review lens and Refactoring already
use for GitNexus.

- When `.gitnexus/` exists and `gitnexus` is on `PATH`, refresh the index with
  `gitnexus analyze --index-only`, then take reach from `gitnexus impact`.
  Otherwise count callers with grep.
- Name the source of each number in the output, so a grep count is never read
  as a graph result.
- The index reflects the last analyzed commit. Report symbols that exist only
  in the working tree as absent from the index, and grep those.
- A missing or failing GitNexus is not an error. Fall back to grep and say so.
  When both lookups fail, report reach as `unknown`.
- Churn and coverage come from Git and the test runner.

The suite's text shows `gitnexus impact` and `gitnexus context` taking a
symbol. The script receives paths. Check the installed CLI's help for a
path query before choosing how to map paths to symbols.

#### Default endpoints

A stated endpoint always wins. These defaults apply when the user states none.

| The repository has | Default endpoint | Independent scrutiny |
| --- | --- | --- |
| A remote and a way to open a pull request | Reviewable PR | Human PR review can be credited. |
| A remote and no pull request tool | Pushed branch, named in the reply | `trail reviewer`, or the user's review of the branch. |
| No remote | Commits on a local branch, with the branch and its diff command in the reply | `trail reviewer`, or the user's review of the branch. |
| No Git repository | `git init`, then the row above | Same as the row above. |

Report scrutiny as pending until one of the listed reviews happens.

### Decisions made on 2026-11-10

The maintainer settled three questions this assessment raised.

1. **Route by table.** Accepted as [Route selection](#route-selection)
   describes: the table first on every task, an optional decision call that can
   only raise the route, and user override in either direction. This replaces
   Feature's instruction not to assign scores for the route itself. The table
   uses categories, not numeric scores, and no model call is required.
2. **Divergence from upstream.** Accepted. Phases 1 to 4 edit upstream-derived
   playbooks and the entry, which raises the cost of each sync. The manifest
   and scripts are port-owned and add none.
3. **Default endpoint.** Accepted as [Default endpoints](#default-endpoints)
   lists, including repositories with no remote.

### Implementation status on 2026-11-10

Phases 1 to 5 and the first item of Phase 6 are implemented on the branch that carries this assessment. [PORTING.md](../PORTING.md#port-additions-beyond-substitution) lists each change under "Routes, plan script, and evidence-bound gates". Every script has model-free tests, and the lint tier runs the two new ratchets. No model ran, so the effect on behavior, cost, and a mid-tier lead is unverified.

| Recommendation | State | Where |
| --- | --- | --- |
| Run rules in the router, routes for every code playbook, one scrutiny rule, endpoint and budget, pin reuse | Done | Mode entry, `references/routes.md`, review lens, four playbooks |
| Manifest and plan script, risk evidence script, entry at 8,000 bytes, daily routes in the entry | Done | `routes.json`, `scripts/plan.py`, `scripts/risk-facts.py`, `references/playbooks.md`, `references/principles.md` |
| Optional decision call that can only raise | Done, switched off | `scripts/second-opinion.py`. Tested against fake CLIs only. |
| Gate evidence bound to a tree, cleanup once per published head, no forced reread, writing lint, opt-in recap, gated publish on demand | Done | `pstack-harness/scripts/gate.py`, `scripts/check-writing.py`, `references/gated-publish.md` |
| One spawn rule, reviewer at or above the lead's tier, printed brief clauses, panels on the intensive route | Done | `references/delegation.md`, `subagents.py clauses`, `routes.json` |
| Context per route, unused-skill report, promises per owner, compensations register | Done | `tools/check-route-bytes.py`, `tools/unused-skills.py`, `ledger.py by-owner`, PORTING.md |
| Lead model and effort in live records | Done | `lead_model` and `lead_effort` in the sealed run metadata |
| Capability-by-workflow support table | Not done | Left out with the harness certification work, at the maintainer's direction. |

Five things differ from the recommendation as written.

- The always-on triggers were not all folded into the manifest. The manifest owns each gate's cadence. Task triggers keep the procedure text that ledger promises quote, and one line that tells the lead to follow the plan's gates.
- The removal check shipped as a ratchet on how many files name a skill, then was removed. That number measures edit cost on disk, which is not suite size. `tools/unused-skills.py` now reports skills nothing loads, for review only.
- Bytes per route live in a new `tools/check-route-bytes.py`. `loading-path.py` is unchanged, because its receipts pin its output.
- The loaded bytes fell less than the entry did. A lightweight Feature now loads about 127 KB of source across its plan, against roughly 150 KB before by the same count. The larger change is frequency: cleanup runs once per push instead of once per commit, and unchanged evidence is reused.
- The sealed metadata change cannot be exercised here. Seventy-five grade-boundary tests need the reviewed macOS runtime and were skipped. Run them there before relying on `lead_model`.

Two risks deserve a targeted look before this merges.

- A generated checklist block for the worklist was tried in 2026-10 and not adopted, because leads stopped keeping a worklist. The plan script prints the items at run time and says it is not the worklist, which differs from that block, but no run has tested it.
- Narrowing `architect` to the intensive route and cleanup to once per push changes two guide promises. The guide, ledger claims, and quotes are updated. The framework asks for independent maintainer review before weakening a promise.

### Outcome wording and the manifest

Commit `7482fc4` gave eleven playbooks outcome-first steps. A review against upstream at `c742dd6` found the idea sound and the execution additive. Skill names sat in the outcome titles, some outcomes named no evidence, a few repeated the next sentence, and the entry did not say which sentences bind.

The follow-up change makes each outcome a strict prefix, as [PORTING.md](../PORTING.md#port-additions-beyond-substitution) now describes. It also settles where outcomes live, by the [rule ownership](framework.md#scope-and-rule-ownership) table.

- **Outcomes stay in the playbook.** A playbook owns the outcomes and their order for its task type. Moving them to `routes.json` would put playbook content in router data, and a lead whose script cannot run would lose them.
- **The manifest holds run policy only.** It keeps the gates and their cadence, the panel list, the skills a lightweight route keeps, and the flags of the seven playbooks that change code or take a risk route. That is the part a script must apply the same way every time, and the part a single edit should be able to subtract.
- **The manifest holds nothing derivable.** File paths and the daily list are gone from it. A playbook with no flag has no entry, so a new upstream playbook needs no manifest change.

The strict prefix keeps nine upstream-derived playbooks comparable with upstream after one sentence per step. No run has measured the rewording.
### What a lightweight Feature loads, by evidence

Size is what a route places in the lead's context, and an instruction needs evidence that the floor model fails without it. This table applies that test to the 16 files a lightweight Feature loads at this branch's head, 128,497 bytes of Markdown plus 4,172 bytes of plan output. `python3 tools/check-route-bytes.py --report` reproduces the sizes. The labels come from results already recorded in this repository. No model ran for this table.

| Loaded file | Bytes | Evidence the lead needs it | Label |
| --- | ---: | --- | --- |
| `playbooks/feature.md` | 15,951 | The edge pass in step 4 showed no gain in delivered code on Claude Code or Codex, a gain in the lead's own tests on one implied edge (3 of 3 against 0 of 3), and about 90 seconds more per run ([2026-11-01](promises/results/2026-11-01-feature-edge-pass.md)). The reuse list rests on one operator taste ballot. The compact route and the preservation steps have no run. | Mixed. Mostly untested. |
| `references/review-lens.md` | 13,818 | In Code review the lens and playbook lifted Claude Sonnet 5 from 6 of 12 to 9 of 12 flaws found, and did not help Codex (1 of 12 against 0 of 12), per PORTING.md's review screen. A Feature reads only its Independent scrutiny section, which has no run. | Shown to help for review. Untested here. |
| `playbooks/opening-a-pr.md` | 12,088 | Static quotes only. | Untested. |
| `deslop` | 11,175 | Live promises check that it runs and cuts seeded slop. No comparison against a lead without it. | Untested for benefit. |
| `references/task-triggers.md` | 10,662 | The "Call the Skill tool with" wording moved a required load from 1 of 3 to 3 of 3 on Claude Code ([phrasing study](../docs/skill-cross-reference-phrasing.md)). The architect trigger did not change behavior: leads skipped the design fan-out under the old and new text ([2026-11-05](promises/results/2026-11-05-architect-trigger.md)). Most other lines have no run. | Mixed. |
| `documentation-impact` | 10,033 | Port addition with no comparison. | Untested. |
| `technical-writing` | 9,069 | No comparison. | Untested. |
| `pstack-harness` | 8,252 | It maps tool names per CLI, which a lead cannot infer. Its worklist fallback moved a posted list from 0 of 5 to 3 of 3 on Claude Code, per PORTING.md. | Functional, with one part shown to help. |
| `poteto-mode/SKILL.md` | 7,996 | The worklist instruction raised structured worklists from 2 of 6 to 4 of 6 on Claude Sonnet 5, and full step lists from 0 of 6 to 3 of 6 on Codex, per PORTING.md's worklist screen. The plan, route, endpoint, and binding text added on this branch has no run. | Mixed. |
| `spec-probes` | 7,028 | Same result as the edge pass above. | No gain in delivered code on the tested specs. |
| `unslop` | 6,089 | A with-and-without corpus exists in `evals/unslop`. No result is committed. | Untested in the record. |
| `references/routes.md` | 5,313 | Added on this branch. | Untested. |
| `no-comments` | 3,193 | No comparison. | Untested. |
| `references/worklist.md` | 2,738 | Covered by the fallback result above. | Shown to help. |
| `references/writing.md` | 2,556 | No comparison. | Untested. |
| `principle-prove-it-works` | 2,536 | In the worklist screen, leads followed 10 to 13 percent of the principle pointers the steps name. No result shows what the leaf changes when it loads. | Untested. |

Three results bear on the whole route.

- The [port value comparison](port-value/results/2026-10-19.md) found that the bare model passed every application task at both stages. For acceptance on those task types the suite's instructions are not shown to be needed. Its oracles did not grade code quality, and it did not activate the mode.
- The [verify-commands pilot](results/2026-11-08-eval-efficiency.md) found no lift on two tasks.
- About 40 KB of this route is five gate skills: `deslop`, `documentation-impact`, `technical-writing`, `unslop`, and `no-comments`. None has a recorded comparison.

So a small part of this route's context has a recorded benefit. It sits in the worklist rule, the load wording, the harness mapping, and the review lens when it is used for review. Everything this branch added is in the untested group. Untested does not mean unneeded. It means the claim that a lead needs the text rests on judgment, so each item is provisional until a targeted comparison settles it.

### Scope left out on purpose

The first review of the suite also found that no task in the repository has
headroom to show that a skill earns its place. Both matched baselines were
saturated. Closing that gap needs new tasks and model runs, which this work
excludes. The retention rule in the framework still applies. Phase 5 only makes
the candidates visible and cheap to remove.

### Basis for these choices

- [How Many Instructions Can LLMs Follow at Once?](https://arxiv.org/abs/2507.11538)
  measured 20 models from 10 to 500 simultaneous instructions. Smaller and
  non-reasoning models degraded early, errors shifted toward omission, and
  earlier instructions were favored. The task was keyword inclusion, so it
  indicates direction, not a threshold for this suite.
- Anthropic's [skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
  advise concise skills, progressive disclosure, utility scripts for
  deterministic operations, and testing on every model tier in use, since
  guidance that suits the strongest model can be insufficient for a smaller one.
- Anthropic's [context engineering guidance](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  states the goal as the smallest set of high-signal tokens that produces the
  outcome, with context loaded when needed.
- This repository's [cross-reference phrasing study](../docs/skill-cross-reference-phrasing.md)
  found that one wording change moved a required skill load from 1 of 3 runs to
  3 of 3 on Claude Code. Loads that depend on the lead noticing a sentence are
  fragile, which favors printing each step's loads.
- The [port value comparison](port-value/results/2026-10-19.md) recorded the
  current port at about 2.6 times the input tokens of native and upstream arms
  with equal acceptance, under the limits the framework states.
- `preserve.py`, `check-models-config.py --resolve`, and `orch` already show
  the pattern recommended here. A script holds the policy and prints the next
  action.

### Not recommended

- A new skill, a risk-scoring model call, or a reviewer panel for any of this.
- Separate instructions per model tier. One structure built for the floor
  serves stronger leads with less text.
- Merging or rewriting principle leaves. They are small, upstream-owned, and
  already load on demand.
- Hill climbing or broad harness runs to tune thresholds in this work.
- Removing any promise. Each cut above goes through the framework's review for
  weakening coverage.
