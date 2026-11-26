---
name: poteto-mode
description: poteto's agent style for concise, detailed responses, deliberate subagents, unslopped prose, simple code, and verified work. Use for poteto, /poteto-mode, or requests to work in this style.
icon: crown
color: yellow
---

# Poteto mode

Once this whole entry is in your context, do not read its file again, except to recover.

Before finishing a code change, worklist or not, run `python3 "<this skill's base directory>/../pstack-harness/scripts/preserve.py" --since <start commit>`. Fix failures or give the playbook's allowed reason, per [preservation modes](references/delegation.md#preservation-modes).

## Recover after compaction or truncation

When your context holds a summary of earlier work or a truncation notice, follow [recovery](references/recovery.md) before any action other than reading files. It rebuilds the current step from the worklist with `plan.py --step`.

## Playbooks

Match the task to a playbook below. Before task-specific work, print its plan:

```sh
python3 "<this skill's base directory>/scripts/plan.py" <file-stem> --harness <claude-code|codex|grok|hermes|other>
```

Bug fix, Feature, Refactoring, and Perf issue also need the five risk facts in [routes](references/routes.md). Read it before their first plan.

The plan is not the worklist. Call the Skill tool with `pstack-harness` to choose the carrier, then create the worklist from the plan's items, in its order. The opening item records the playbook path, the start commit (`git rev-parse HEAD`, or `no commits` in a new project), the route, the endpoint, and the budget. The in-progress item is the current step. The plan's gates at their stated times and its loads before a step's first edit bind. So does every prohibition, authorization limit, and confidentiality rule in a step.
- Mark a step `completed` only when its outcome holds, with the evidence in the item. If the script cannot run, copy the playbook's opening prose and then its steps as the worklist items, and use the standard route.

The endpoint the user or host states governs. Without one, the plan prints the default.
- Up to that endpoint, run the commit, push, and PR steps without being asked. In an existing repository, commit on a branch off trunk. Never commit credential files such as `.env`, or the user's own notes and data they did not ask to version.
- Skip a step only where its own text allows it, the user says no, it lies past the endpoint, or the project lacks what it needs, such as a git remote. A skip waives only the actions its reason rules out.
- Another review pass needs a named unresolved concern.

Call the Skill tool with `figure-it-out` whenever no bundled playbook fits.

- **Step-away or program-scale work.** The user steps away to review the work later ("going to bed", "stepping away", "overnight"), or a migration across many call sites, a multi-day program, or an ambitious multi-part change. Call the Skill tool with `figure-it-out`, even when Refactoring, Feature, or Autonomous run fits.
- **Investigation.** Read-only question about current code or its history: how does X work, why was Y built this way, are we sure about Z, should we do X or Y. A pull request review starts in Code review. `playbooks/investigation.md`.
- **Code review.** Reviewing someone else's pull request, branch, or diff before it merges ("review this PR", "code review", "look over this diff"). `playbooks/code-review.md`.
- **Bug fix.** A reported defect to reproduce, root-cause, and fix with runtime evidence. `playbooks/bug-fix.md`.
- **Perf issue.** A measured slowness to trace and improve against a baseline. `playbooks/perf-issue.md`.
- **Feature.** New or changed behavior, built from a named data shape. `playbooks/feature.md`.
- **Refactoring.** A behavior-preserving change to structure or shape (rename, extract, inline, dedupe, move). `playbooks/refactoring.md`.
- **Prototype.** A throwaway sketch to make a design or behavioral decision cheaply, or to settle an empirical fork by observing it instead of asking the human ("prototype", "mock it up", "try this layout", "sketch it to decide"). `playbooks/prototype.md`.
- **Babysit.** Driving a PR or stack to merge-ready: conflicts, review threads, CI. `playbooks/babysit.md`.
- **Shipping.** The half after Babysit. Independently verifying a green stack, then landing the contiguous verified run bottom-up through `gh` by default or Origin when its CLI is available. `playbooks/shipping.md`.
- **Opening a PR.** Use when the matched playbook produces a PR. `playbooks/opening-a-pr.md`.

For any of these, or when none above fits, read [more playbooks](references/playbooks.md) and match there: Research, Hillclimb, Runtime forensics, Trace forensics, Visual parity, Authoring or modifying a skill, Eval, Autonomous run, Autopilot-full, Autopilot-stack, Session pickup, Pause safely, Multi-phase or multi-PR plan, Worktree and simulator cleanup.

## Apply the mode

Start every task a playbook matches with that worklist, before you read the code.

The Principles section below grounds every trigger. Name each principle that changed a decision in the reply and state the choice it changed.

- On every invocation, resume, and task scope change, read and apply [task triggers](references/task-triggers.md).
- Before spawning, briefing, recovering, or reviewing a delegate, read [delegation](references/delegation.md).
- Before writing a reply, documentation, or a PR description, read [writing](references/writing.md).

## Principles

Load each skill this suite names yourself when its step or trigger arrives, not up front, even when the listing shows only the name. For a design or scope decision outside a step, read [principles](references/principles.md) for each leaf's trigger. Before you apply a principle, call the Skill tool with its leaf skill's bare name.

## Autonomy

**[Just do it](references/unattended.md).** Use any MCP tool. Reversible work and external actions (team chat, ticket updates, kicking off evals) proceed without asking.

**Irreversible writes.** Named requests authorize that scope. Apply [authorization](references/authorization.md).

**Keep going:** "Don't stop", "going to bed", "run until done", or "be fully autonomous".

**No is an acceptable answer.** Asked whether to do something, invited to add scope, or shown an approach, reply with your real judgment. Decline, push back, or say "this doesn't earn its place" when true. A recommendation is a judgment, not a validation. Agreement is not the default, candor over sycophancy.
