# Recover after compaction or truncation

Compaction replaces earlier context with a summary. Recover when your context holds a summary of earlier work or a truncation notice, before your next project write, commit, or spawn. Finish each step before the next.

1. **Find the step.** The worklist's opening item names the playbook path, start commit, route, and endpoint, and the item in progress is the current step. Use the task record or resume note when no worklist came back.
2. **Count what came back.** A file is in context when its whole text appears after the summary, as a skill the harness attached again does. Read in full, one file per tool response, each of these that is not: the [poteto-mode entry](../SKILL.md) and the [task triggers](task-triggers.md).
3. **Print the current step.** Run `python3 "<this skill's base directory>/scripts/plan.py" <playbook> --step <n> --route <route> --harness <claude-code|codex|grok|hermes|other>` and apply its text. It stands in for the whole playbook, so leave the playbook file unread. Load each skill the step names whose whole text is not after the summary. If the script cannot run, read the playbook file instead.
4. **Reconcile.** Keep completed items, outstanding gates, and existing grants as the worklist records them. Rerun a check the step requires instead of trusting a remembered result. Continue the same task without a new pause for the user.

A read that comes back cut or reports truncation is unfinished: read the missing part before acting. If a file stays unavailable, report its exact path and hold only the actions that need it. Read the [runtime retention evidence](../../pstack-harness/references/skill-retention.md) when retention or restoration affects a decision.
