---
description: pstack per-role model choices (overrides skill defaults)
---
# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit the model); in the arena cross-judge pool such an entry never judges. Alias entries in a panel list still count toward its fan-out, except in a design comparison the resolver marks a same-model skip.
# `model@effort` pins the reasoning effort (none, low, medium, high, xhigh, max, or ultra; the lint rejects an effort the model cannot take). A line without a suffix gets setup-pstack's effort policy, never another file's suffix (floor high on Codex and Hermes and medium on Claude Code when the line names a model, the session effort on Grok Build).
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
routine: sonnet@medium
default: inherit-parent

## claude-code
feature, refactoring: sonnet@medium
bug-fix: sonnet@high
perf-issue: sonnet@high
hillclimb: sonnet@high
judgment and prose: opus@xhigh
hardest tasks: opus@xhigh
how explorer: sonnet@medium
how explainer: opus@xhigh
why investigators: sonnet@medium
why synthesizer: opus@xhigh
reflect tooling: opus@high
reflect judgment, divergent, synthesizer: opus@xhigh
arena runners: fable@xhigh, opus@high, sonnet@high
arena cross-judge pool: fable@xhigh, opus@high, sonnet@high
swarm workers: sonnet@high
architect runners: fable@xhigh, opus@high, sonnet@high
interrogate reviewers: fable@xhigh, opus@high, sonnet@high
trail reviewer: opus@high
routine: sonnet@medium

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
trail reviewer: gpt-6-astra@high
routine: gpt-6-luna@medium
