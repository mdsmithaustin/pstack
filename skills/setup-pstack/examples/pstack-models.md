---
description: pstack per-role model choices (overrides skill defaults)
---
# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit the model); in the arena cross-judge pool such an entry never judges. Alias entries in a panel list still count toward its fan-out, except in a design comparison the resolver marks a same-model skip.
# `model@effort` pins the reasoning effort (none, low, medium, high, xhigh, max, or ultra; the lint rejects an effort the model cannot take). A line without a suffix gets setup-pstack's effort policy, never another file's suffix (floor high on Codex and Hermes and medium on Claude Code when the line names a model, the session effort on Grok Build).
# `## codex`, `## claude-code`, `## grok`, `## hermes` sections override flat lines in either file, for that harness only.
# defaults: 3
# budget: default (keep as written)
feature, refactoring: opus
bug-fix: opus
perf-issue: opus
hillclimb: opus
judgment and prose: opus
how explorer: opus
how explainer: opus
why investigators: opus
why synthesizer: opus
reflect tooling: opus
reflect judgment, divergent, synthesizer: opus
arena runners: fable, opus, inherit-parent
arena cross-judge pool: opus
swarm workers: opus
architect runners: fable, opus, inherit-parent
interrogate reviewers: fable, opus, inherit-parent
trail reviewer: opus
routine: opus@medium
default: inherit-parent

## claude-code
feature, refactoring: opus@xhigh
bug-fix: opus@xhigh
perf-issue: opus@xhigh
hillclimb: opus@xhigh
judgment and prose: opus@xhigh
how explorer: opus@xhigh
how explainer: opus@xhigh
why investigators: opus@xhigh
why synthesizer: opus@xhigh
reflect tooling: opus@high
reflect judgment, divergent, synthesizer: opus@xhigh
arena runners: fable@high, opus@high, inherit-parent
arena cross-judge pool: opus@high
swarm workers: opus@high
architect runners: fable@high, opus@high, inherit-parent
interrogate reviewers: fable@high, opus@high, inherit-parent
trail reviewer: opus@high
routine: opus@medium

## codex
feature, refactoring: gpt-6-sol@xhigh
bug-fix: gpt-6-sol@xhigh
perf-issue: gpt-6-sol@xhigh
hillclimb: gpt-6-sol@xhigh
judgment and prose: gpt-6-sol@xhigh
how explorer: gpt-6-sol@xhigh
how explainer: gpt-6-sol@xhigh
why investigators: gpt-6-sol@xhigh
why synthesizer: gpt-6-sol@xhigh
reflect tooling: gpt-6-sol@high
reflect judgment, divergent, synthesizer: gpt-6-sol@xhigh
arena runners: gpt-6-astra@high, gpt-6-sol@high, inherit-parent
arena cross-judge pool: gpt-6-astra@high, gpt-6-sol@high
swarm workers: gpt-6-sol@high
architect runners: gpt-6-astra@high, gpt-6-sol@high, inherit-parent
interrogate reviewers: gpt-6-astra@high, gpt-6-sol@high, inherit-parent
trail reviewer: gpt-6-astra@high
routine: gpt-6-sol@medium
