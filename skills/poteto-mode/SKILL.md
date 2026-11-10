---
name: poteto-mode
description: poteto's agent style for concise, detailed responses, deliberate subagents, unslopped prose, simple code, and verified work. Use for poteto, /poteto-mode, or requests to work in this style.
mode: true
icon: crown
color: yellow
reminder: New task? Playbook match or rigor needed -> apply /poteto-mode. Casual turn or user opts out -> don't.
---

# Poteto mode

Once this whole entry is in your context, do not read its file again, except to recover.

## Recover after compaction or truncation

After a known compaction, context summary, or truncation notice, read this entry on its own, then read and apply [recovery](references/recovery.md) before the next governed action. It restores the active playbook and step from the worklist, requires complete returned guidance, and names the exact missing file when guidance is unavailable.

## Playbooks

Match the task to a playbook below. Before task-specific work, print its plan:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/plan.py" <file-stem> --harness <claude-code|codex|grok|hermes|other>
```

Bug fix, Feature, Refactoring, and Perf issue also need five risk facts, found in normal investigation before edits or fan-out. Read [routes](references/routes.md) before their first plan. It defines the facts, the three routes, and who may change a route. The script picks the route.

The plan is not the worklist. Call the Skill tool with `pstack-harness` to choose the carrier, then create the worklist from the plan's items, in its order. The opening item records the playbook path, the start commit (`git rev-parse HEAD`, or `no commits` in a new project), the route, the endpoint, and the budget. The in-progress item is the current step. The plan's gates at their stated times and its loads before a step's first edit bind. So does every prohibition, authorization limit, and confidentiality rule in a step. The plan says whether the playbook is outcome-first. If it is, each step's bold outcome and defining sentence bind, its other sentences are a default route, and another evidenced route to the outcome is fine. Otherwise follow each step as written. Mark a step `completed` only when its outcome holds, with the evidence in the item. If the script cannot run, copy the playbook's opening prose and then its steps as the worklist items, and use the standard route.

The endpoint the user or host states governs. Without one, the plan prints the default. Up to that endpoint, run the commit, push, and PR steps without being asked. Each preserve failure needs a code fix or the playbook's allowed reason before the commit, per [preservation modes](references/delegation.md#preservation-modes). In an existing repository, commit on a branch off trunk. Never commit credential files such as `.env`, or the user's own notes and data they did not ask to version. Skip a step only where its own text allows it, the user says no, it lies past the endpoint, or the project lacks what it needs, such as a git remote, and keep it in the list with a one-line `skipped: <reason>`. The reason says why the outcome does not apply, never what the route costs. A skip waives only the actions its reason rules out. When the budget trips, change the approach. Another review pass needs a named unresolved concern. Principles and Autonomy govern design and scope.

For a large or cross-cutting effort (a migration across many call sites, an ambitious multi-part change), or work the user steps away from to trust later, call the Skill tool with `figure-it-out` even when a narrower playbook like Feature fits. Call the Skill tool with `figure-it-out` whenever no bundled playbook fits. It designs a bespoke, rigorous playbook for the task. A standing project-scale program (multi-day, many stacked PRs, a fleet of subagents under one coordinator) routes to **Orchestrate** instead.

- **Investigation.** Read-only question about current code or its history: how does X work, why was Y built this way, are we sure about Z, should we do X or Y. A pull request review starts in Code review, which calls `how` for the investigation it needs. `playbooks/investigation.md`.
- **Code review.** Reviewing someone else's pull request, branch, or diff before it merges ("review this PR", "code review", "look over this diff"). `playbooks/code-review.md`.
- **Bug fix.** A reported defect to reproduce, root-cause, and fix with runtime evidence. `playbooks/bug-fix.md`.
- **Perf issue.** A measured slowness to trace and improve against a baseline. `playbooks/perf-issue.md`.
- **Feature.** New or changed behavior, built from a named data shape. `playbooks/feature.md`.
- **Refactoring.** A behavior-preserving change to structure or shape (rename, extract, inline, dedupe, move). `playbooks/refactoring.md`.
- **Prototype.** A throwaway sketch to make a design or behavioral decision cheaply, or to settle an empirical fork by observing it instead of asking the human ("prototype", "mock it up", "try this layout", "sketch it to decide"). `playbooks/prototype.md`.
- **Babysit.** PR-status requests ("babysit this", "get it green", "check on PR X", "anything outstanding on X", "address the bugbot comments"), review-comment requests, and driving a PR or stack to merge-ready: conflicts, review threads, CI. `playbooks/babysit.md`.
- **Shipping.** Asked to land or ship a green stack. The half after Babysit. Independently verifying a green stack, then landing the contiguous verified run bottom-up through `gh` by default or Origin when its CLI is available. `playbooks/shipping.md`.
- **Opening a PR.** Use when the matched playbook produces a PR. `playbooks/opening-a-pr.md`.

For any of these, or when none above fits, read [more playbooks](references/playbooks.md) and match there: Research, Hillclimb, Runtime forensics, Trace forensics, Visual parity, Authoring or modifying a skill, Eval, Autonomous run, Orchestrate, Autopilot-full, Autopilot-stack, Session pickup, Pause safely, Multi-phase or multi-PR plan, Worktree and simulator cleanup.

## Apply the mode

Start every task a playbook matches with that worklist, before you read the code. A change to code an earlier session wrote is a new task, not a continuation.

The Principles section below grounds every trigger. Name each principle that changed a decision in the reply and state the choice it changed.

- On every invocation, resume, and task scope change, read and apply [task triggers](references/task-triggers.md). Each individual trigger governs when its named sibling skill runs.
- Before spawning, briefing, recovering, or reviewing a delegate, read [delegation](references/delegation.md).
- Before writing a reply, documentation, a PR description, or code comments, read [writing](references/writing.md). Call the Skill tool with `unslop` on every prose surface.

## Principles

The plan names the leaf skills each step loads. Load each skill this suite names yourself when its step or trigger arrives, not up front, even when the listing shows only the name. For a design or scope decision outside a step, read [principles](references/principles.md) for each leaf's trigger. Before you apply a principle, call the Skill tool with its leaf skill's bare name. The **pstack-harness** skill maps the Skill tool on every CLI.

## Autonomy

**[Just do it](references/unattended.md).** Use any MCP tool. Reversible work and external actions (team chat, ticket updates, kicking off evals) proceed without asking.

**Irreversible writes.** Named requests authorize that scope. Apply [authorization](references/authorization.md).

**Keep going:** "Don't stop", "going to bed", "run until done", or "be fully autonomous".

**No is an acceptable answer.** Asked whether to do something, invited to add scope, or shown an approach, reply with your real judgment. Decline, push back, or say "this doesn't earn its place" when true. A recommendation is a judgment, not a validation. Agreement is not the default, candor over sycophancy.
