---
name: principle-prove-it-works
description: "Apply after completing a task, before declaring done. Verify against the real artifact (run the feature, read the actual value, inspect the diff), not a proxy, self-report, or 'it compiles.'"
---

# Prove It Works

Verify every output by checking the real thing directly: run the feature, read the actual value, inspect the diff. Proxies (file mtimes, self-reports, cached output, "it compiles") do not count. When a check fails, suspect the observation method before the system.

## Account for the accepted scope

Check against the original accepted requirements. A plan, summary, or delegation cannot silently narrow them. Link each requirement to evidence or an explicit gap in the existing task record. An unmet requirement prevents a full completion claim. Preserve any `backstop` or `judgment` tags and record authorized scope changes separately. Reuse a runner's record when one exists.

When the work includes a threat model or security review, reconcile every declared threat with mitigation evidence at the threatened boundary. A claim of mitigation is not evidence. Record accepted risk with its authorized owner, transferred responsibility with its owner and evidence, or an open gap. Unresolved threats stay visible in the completion verdict.

## Tie proof to the result

Record the artifact each check exercised, its revision when applicable, and the relevant environment. After combining changes, rerun checks for the affected paths on the integrated result. Separate passing branches do not prove their combination.

Run a named acceptance helper when the task or project requires it. If it cannot run, report the gap. Justify any replacement against the same acceptance criteria before treating it as equivalent.

## Script the check when you can

A deterministic script that reruns the comparison beats a one-time look. Keep its output where the human can see it. Call the Skill tool with `show-me-your-work` for trail storage and evidence-retention rules.
