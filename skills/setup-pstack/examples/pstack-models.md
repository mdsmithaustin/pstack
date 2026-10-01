---
description: pstack per-role model choices (overrides skill defaults)
---
# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit the model). Alias entries in a panel list still count toward its fan-out.
# `model@effort` pins the reasoning effort (none, low, medium, high, xhigh, max, or ultra; the lint rejects an effort the model cannot take). A line without a suffix gets setup-pstack's effort policy, never another file's suffix (floor high on Codex and Hermes when the line names a model, the session effort on Claude Code and Grok Build).
# `## codex`, `## claude-code`, `## grok`, `## hermes` sections override flat lines in either file, for that harness only.
# budget: default (keep as written)
feature, refactoring: sonnet
bug-fix: sonnet
perf-issue: sonnet
hillclimb: sonnet
judgment and prose: opus
hardest tasks: opus
how explorer: sonnet
how explainer: opus
why investigators: sonnet
why synthesizer: opus
reflect tooling: opus
reflect judgment, divergent, synthesizer: opus
arena runners: fable, opus, sonnet
arena cross-judge pool: fable, opus, sonnet
swarm workers: sonnet
architect runners: fable, opus, sonnet
interrogate reviewers: fable, opus, sonnet
trail reviewer: opus
default: inherit-parent

## codex
feature, refactoring: gpt-6-sol@high
bug-fix: gpt-6-sol@xhigh
perf-issue: gpt-6-sol@xhigh
hillclimb: gpt-6-sol@xhigh
judgment and prose: gpt-6-sol@max
hardest tasks: gpt-6-sol@max
how explorer: gpt-6-sol@high
how explainer: gpt-6-sol@max
why investigators: gpt-6-sol@high
why synthesizer: gpt-6-sol@max
reflect tooling: gpt-6-sol@xhigh
reflect judgment, divergent, synthesizer: gpt-6-sol@max
arena runners: gpt-6-sol@max, gpt-6-sol@xhigh, gpt-6-luna@xhigh
arena cross-judge pool: gpt-6-sol@max, gpt-6-sol@xhigh, gpt-6-luna@xhigh
swarm workers: gpt-6-luna@xhigh
architect runners: gpt-6-sol@max, gpt-6-sol@xhigh, gpt-6-luna@xhigh
interrogate reviewers: gpt-6-sol@max, gpt-6-sol@xhigh, gpt-6-luna@xhigh
trail reviewer: gpt-6-luna@xhigh
