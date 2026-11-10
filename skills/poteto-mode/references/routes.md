# Routes

Read this reference before the first plan of a Bug fix, Feature, Refactoring, or Perf issue task, and when a route, endpoint, or budget is in question. It holds the rules for how a task is run. Playbooks cite it and do not restate it.

## Record five facts

Record each fact as `low`, `material`, or `unknown`, with one line of evidence. Find the evidence in normal investigation, before edits or fan-out. Use Git history, callers, static checks, and existing test results before your own judgment. For history, caller, and test evidence on the paths you will touch, run:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/risk-facts.py" [--symbol <name>]... <path>...
```

| Fact | Flag | Evidence to look for |
|---|---|---|
| Consequence | `--consequence` | Data loss, permissions, incorrect results, compatibility, and user-visible disruption. |
| Reach | `--reach` | Shared callers, public interfaces, dependencies, and affected workflows. |
| Uncertainty | `--uncertainty` | Unclear requirements, unfamiliar code, weak tests, contested design, and behavior you cannot reproduce. |
| Accumulated complexity | `--complexity` | Repeated changes, growing conditionals, duplication, exceptions, and recurring repairs. Apply the review lens's [Accumulated complexity](review-lens.md#accumulated-complexity) check when extending code. |
| Reversibility and detection | `--reversibility` | Whether a failure is visible, whether a rollback exists, and whether recovery preserves data. |

`unknown` is an honest answer. A `low` with no evidence counts as `unknown`. File or line counts do not establish low risk. Do not commission a model to classify the risk.

## The three routes

The plan script maps the facts to a route. It needs no model and gives the same answer on every CLI.

- **Lightweight.** Every fact is low with evidence. Work directly. Spawn no investigation or implementation delegate and no panel. Load only the skills the plan lists. Keep preservation, real-surface proof, and independent scrutiny.
- **Standard.** At least one fact is not low. Follow every step of the playbook. Compare design options yourself and record them. The panels (`architect`, `arena`, `interrogate`, `swarm`) stay unloaded. This limit covers only the four playbooks this reference routes. Any other playbook keeps the panels its own steps require.
- **Intensive.** Consequence is not low, and uncertainty or reversibility is not low. Follow every step, with the panels where a step or trigger names them.

When new evidence changes a fact, rerun the plan script and expand the worklist before further edits. Retain the opening item and valid completed evidence.

## Who can change the route

- The user can set the route in either direction. Pass `--user-route <route>`. The worklist records `route: <name> (user)`.
- You can raise the route with `--raise-to <route> --reason <why>`. You cannot lower it below the table's result.
- A second opinion can raise a fact. It is off unless the repository holds `.agents/pstack-second-opinion` naming `codex` or `claude`. When it is on and the `risk-facts.py` evidence disagrees with a fact you recorded as low, run `python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/second-opinion.py"` with the same facts, `--task`, and `--out <file>`, then pass `--second-opinion <file>` to the plan script. An unavailable answer changes nothing.
- No route change skips a gate the repository requires, or the [authorization](authorization.md) that an irreversible action needs.

## Endpoint

The endpoint is how far the task goes. The user's stated endpoint governs, and so does a host instruction such as "do not open a pull request unless asked". An endpoint is one of evidence, local commits, a pushed branch, a reviewable PR, or merge. Merge always needs its own authorization.

With no stated endpoint, use the furthest reviewable state the repository supports. The plan prints it.

| The repository has | Default endpoint |
|---|---|
| A remote and a way to open a pull request | A reviewable PR. |
| A remote and no pull request tool | A pushed branch, named in the reply. |
| No remote | Commits on a local branch. Give the branch and its diff command in the reply. |
| No Git repository | Run `git init`, then use the row above. |

Steps past the endpoint stay in the worklist as `skipped: <reason>`.

## Budget and stopping

Write the budget in the opening item as the event that makes you change approach, such as two failed attempts on one premise or a repair that grows past the planned files. When it trips, change the approach and say so. Ask the user when the next step changes agreed scope, cost limits, or authority.

Stop reviewing when the acceptance criteria hold and no material uncertainty remains. Another pass needs a named unresolved concern. After a repair, recheck the affected behavior and newly exposed risks only. Reuse valid evidence for unchanged scope. For a gate the plan marks tree-bound, test whether its evidence still describes the current tree:

```sh
python3 "${PSTACK_SKILLS_ROOT:?}/pstack-harness/scripts/gate.py" check <gate>
```

## Independent scrutiny

Every code change gets independent scrutiny. Follow the review lens's [Independent scrutiny](review-lens.md#independent-scrutiny) section at the playbook's proof step.
