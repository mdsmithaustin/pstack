---
description: pstack per-role model choices (overrides skill defaults)
---
# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit the model). Alias entries in a panel list still count toward its fan-out.
# `model@effort` pins the reasoning effort (none, low, medium, high, xhigh, max; ultra only on gpt-5.6-sol). No suffix: the harness skill's policy applies (floor high).
# `## codex`, `## claude-code`, `## hermes` sections override the lines above for that harness only.
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
feature, refactoring: gpt-5.6-terra@high
bug-fix: gpt-5.6-terra@xhigh
perf-issue: gpt-5.6-terra@xhigh
hillclimb: gpt-5.6-terra@xhigh
judgment and prose: gpt-5.6-sol@max
hardest tasks: gpt-5.6-sol@max
how explorer: gpt-5.6-terra@high
how explainer: gpt-5.6-sol@max
why investigators: gpt-5.6-terra@high
why synthesizer: gpt-5.6-sol@max
reflect tooling: gpt-5.6-sol@xhigh
reflect judgment, divergent, synthesizer: gpt-5.6-sol@max
arena runners: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high
arena cross-judge pool: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high
swarm workers: gpt-5.6-terra@high
architect runners: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high
interrogate reviewers: gpt-5.6-sol@max, gpt-5.6-sol@xhigh, gpt-5.6-terra@high
trail reviewer: gpt-5.6-terra@xhigh
